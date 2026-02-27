# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the workspace configuration module."""

from pathlib import Path

import pytest

from archml.workspace import (
    GitPathImport,
    LocalPathImport,
    WorkspaceConfig,
    WorkspaceConfigError,
    load_workspace_config,
)


# ###############
# Helpers
# ###############


def _write_config(tmp_path: Path, content: str) -> Path:
    """Write a workspace config file and return its path."""
    config_file = tmp_path / ".archml-workspace.yaml"
    config_file.write_text(content, encoding="utf-8")
    return config_file


# ###############
# Normal Cases
# ###############


def test_minimal_config(tmp_path: Path) -> None:
    """A config with only build-directory parses to a WorkspaceConfig with no imports."""
    config_file = _write_config(tmp_path, "build-directory: .archml-build\n")
    config = load_workspace_config(config_file)

    assert isinstance(config, WorkspaceConfig)
    assert config.build_directory == ".archml-build"
    assert config.source_imports == []


def test_config_with_local_path_import(tmp_path: Path) -> None:
    """A local-path source import is parsed into a LocalPathImport."""
    content = """\
build-directory: .build
source-imports:
  - name: common
    local-path: ./libs/common
"""
    config = load_workspace_config(_write_config(tmp_path, content))

    assert len(config.source_imports) == 1
    imp = config.source_imports[0]
    assert isinstance(imp, LocalPathImport)
    assert imp.name == "common"
    assert imp.local_path == "./libs/common"


def test_config_with_git_import(tmp_path: Path) -> None:
    """A git-repository source import is parsed into a GitPathImport."""
    content = """\
build-directory: .build
source-imports:
  - name: shared
    git-repository: https://github.com/example/repo
    revision: main
"""
    config = load_workspace_config(_write_config(tmp_path, content))

    assert len(config.source_imports) == 1
    imp = config.source_imports[0]
    assert isinstance(imp, GitPathImport)
    assert imp.name == "shared"
    assert imp.git_repository == "https://github.com/example/repo"
    assert imp.revision == "main"


def test_config_with_mixed_imports(tmp_path: Path) -> None:
    """Multiple imports of different kinds are all parsed correctly."""
    content = """\
build-directory: dist/archml
source-imports:
  - name: local_lib
    local-path: ./internal/lib
  - name: external_repo
    git-repository: https://github.com/org/project
    revision: v2.3.1
  - name: another_local
    local-path: ../shared
"""
    config = load_workspace_config(_write_config(tmp_path, content))

    assert config.build_directory == "dist/archml"
    assert len(config.source_imports) == 3

    assert isinstance(config.source_imports[0], LocalPathImport)
    assert config.source_imports[0].name == "local_lib"
    assert config.source_imports[0].local_path == "./internal/lib"

    assert isinstance(config.source_imports[1], GitPathImport)
    assert config.source_imports[1].name == "external_repo"
    assert config.source_imports[1].revision == "v2.3.1"

    assert isinstance(config.source_imports[2], LocalPathImport)
    assert config.source_imports[2].name == "another_local"


def test_empty_source_imports_list(tmp_path: Path) -> None:
    """An explicit empty source-imports list is valid."""
    content = """\
build-directory: .build
source-imports: []
"""
    config = load_workspace_config(_write_config(tmp_path, content))
    assert config.source_imports == []


# ###############
# Error Cases
# ###############


def test_file_not_found(tmp_path: Path) -> None:
    """Loading a non-existent file raises WorkspaceConfigError."""
    missing = tmp_path / "missing.yaml"
    with pytest.raises(WorkspaceConfigError, match="not found"):
        load_workspace_config(missing)


def test_invalid_yaml_syntax(tmp_path: Path) -> None:
    """A file with invalid YAML raises WorkspaceConfigError."""
    config_file = _write_config(tmp_path, "build-directory: [\nbroken yaml")
    with pytest.raises(WorkspaceConfigError, match="Invalid YAML"):
        load_workspace_config(config_file)


def test_not_a_mapping(tmp_path: Path) -> None:
    """A YAML file that is not a mapping raises WorkspaceConfigError."""
    config_file = _write_config(tmp_path, "- just a list\n")
    with pytest.raises(WorkspaceConfigError, match="must be a YAML mapping"):
        load_workspace_config(config_file)


def test_missing_build_directory(tmp_path: Path) -> None:
    """A config without build-directory raises WorkspaceConfigError."""
    config_file = _write_config(tmp_path, "source-imports: []\n")
    with pytest.raises(WorkspaceConfigError, match="build-directory"):
        load_workspace_config(config_file)


def test_build_directory_not_a_string(tmp_path: Path) -> None:
    """A non-string build-directory raises WorkspaceConfigError."""
    config_file = _write_config(tmp_path, "build-directory: 42\n")
    with pytest.raises(WorkspaceConfigError, match="build-directory"):
        load_workspace_config(config_file)


def test_source_imports_not_a_list(tmp_path: Path) -> None:
    """A non-list source-imports value raises WorkspaceConfigError."""
    content = """\
build-directory: .build
source-imports: not-a-list
"""
    with pytest.raises(WorkspaceConfigError, match="source-imports.*list"):
        load_workspace_config(_write_config(tmp_path, content))


def test_import_entry_not_a_mapping(tmp_path: Path) -> None:
    """A non-mapping import entry raises WorkspaceConfigError."""
    content = """\
build-directory: .build
source-imports:
  - just a string
"""
    with pytest.raises(WorkspaceConfigError, match="YAML mapping"):
        load_workspace_config(_write_config(tmp_path, content))


def test_import_missing_name(tmp_path: Path) -> None:
    """An import entry without a name raises WorkspaceConfigError."""
    content = """\
build-directory: .build
source-imports:
  - local-path: ./libs
"""
    with pytest.raises(WorkspaceConfigError, match="'name'"):
        load_workspace_config(_write_config(tmp_path, content))


def test_import_both_local_and_git(tmp_path: Path) -> None:
    """Specifying both local-path and git-repository raises WorkspaceConfigError."""
    content = """\
build-directory: .build
source-imports:
  - name: conflict
    local-path: ./libs
    git-repository: https://github.com/example/repo
    revision: main
"""
    with pytest.raises(WorkspaceConfigError, match="not both"):
        load_workspace_config(_write_config(tmp_path, content))


def test_import_neither_local_nor_git(tmp_path: Path) -> None:
    """An import with neither local-path nor git-repository raises WorkspaceConfigError."""
    content = """\
build-directory: .build
source-imports:
  - name: incomplete
"""
    with pytest.raises(WorkspaceConfigError, match="local-path.*git-repository"):
        load_workspace_config(_write_config(tmp_path, content))


def test_git_import_missing_revision(tmp_path: Path) -> None:
    """A git import without revision raises WorkspaceConfigError."""
    content = """\
build-directory: .build
source-imports:
  - name: shared
    git-repository: https://github.com/example/repo
"""
    with pytest.raises(WorkspaceConfigError, match="'revision'"):
        load_workspace_config(_write_config(tmp_path, content))
