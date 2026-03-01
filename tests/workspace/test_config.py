# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the workspace configuration module."""

import pytest

from archml.workspace.config import (
    GitPathImport,
    LocalPathImport,
    WorkspaceConfig,
    WorkspaceConfigError,
    find_workspace_root,
    load_workspace_config,
)

# ###############
# Public Interface
# ###############


def test_load_minimal_config(tmp_path):
    """A config with only build-directory and no source-imports is valid."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text("build-directory: build\n", encoding="utf-8")

    config = load_workspace_config(cfg_file)

    assert isinstance(config, WorkspaceConfig)
    assert config.build_directory == "build"
    assert config.source_imports == []


def test_load_config_with_local_path_import(tmp_path):
    """A source import with local-path is parsed as LocalPathImport."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: out\nsource-imports:\n  - name: common\n    local-path: src/common\n",
        encoding="utf-8",
    )

    config = load_workspace_config(cfg_file)

    assert config.build_directory == "out"
    assert len(config.source_imports) == 1
    imp = config.source_imports[0]
    assert isinstance(imp, LocalPathImport)
    assert imp.name == "common"
    assert imp.local_path == "src/common"


def test_load_config_with_git_import(tmp_path):
    """A source import with git-repository and revision is parsed as GitPathImport."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: out\n"
        "source-imports:\n"
        "  - name: external\n"
        "    git-repository: https://github.com/example/repo\n"
        "    revision: main\n",
        encoding="utf-8",
    )

    config = load_workspace_config(cfg_file)

    assert len(config.source_imports) == 1
    imp = config.source_imports[0]
    assert isinstance(imp, GitPathImport)
    assert imp.name == "external"
    assert imp.git_repository == "https://github.com/example/repo"
    assert imp.revision == "main"


def test_load_config_with_mixed_imports(tmp_path):
    """A config may contain both local and git source imports."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: out\n"
        "source-imports:\n"
        "  - name: local-lib\n"
        "    local-path: libs/local\n"
        "  - name: remote-lib\n"
        "    git-repository: https://github.com/example/remote\n"
        "    revision: v1.0\n",
        encoding="utf-8",
    )

    config = load_workspace_config(cfg_file)

    assert len(config.source_imports) == 2
    assert isinstance(config.source_imports[0], LocalPathImport)
    assert isinstance(config.source_imports[1], GitPathImport)


def test_load_config_with_empty_source_imports(tmp_path):
    """An explicit empty source-imports list is accepted."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\nsource-imports: []\n",
        encoding="utf-8",
    )

    config = load_workspace_config(cfg_file)

    assert config.source_imports == []


def test_error_file_not_found(tmp_path):
    """Loading a nonexistent file raises WorkspaceConfigError."""
    missing = tmp_path / "no-such-file.yaml"

    with pytest.raises(WorkspaceConfigError, match="Cannot read workspace config"):
        load_workspace_config(missing)


def test_error_invalid_yaml_syntax(tmp_path):
    """A file with invalid YAML raises WorkspaceConfigError."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text("build-directory: [\nbad yaml", encoding="utf-8")

    with pytest.raises(WorkspaceConfigError, match="Invalid YAML"):
        load_workspace_config(cfg_file)


def test_error_missing_build_directory(tmp_path):
    """Omitting build-directory raises WorkspaceConfigError."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text("source-imports: []\n", encoding="utf-8")

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)


def test_error_top_level_not_a_mapping(tmp_path):
    """A YAML file whose top-level value is not a mapping raises WorkspaceConfigError."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text("- item1\n- item2\n", encoding="utf-8")

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)


def test_error_source_imports_not_a_list(tmp_path):
    """source-imports must be a list; a scalar value raises WorkspaceConfigError."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\nsource-imports: not-a-list\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)


def test_error_import_both_local_and_git(tmp_path):
    """Specifying both local-path and git-repository raises WorkspaceConfigError."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: conflict\n"
        "    local-path: some/path\n"
        "    git-repository: https://github.com/example/repo\n"
        "    revision: main\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)


def test_error_import_neither_local_nor_git(tmp_path):
    """An import entry with only a name (no local-path or git-repository) raises WorkspaceConfigError."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\nsource-imports:\n  - name: incomplete\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)


def test_error_git_import_missing_revision(tmp_path):
    """A git import without revision raises WorkspaceConfigError."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: external\n"
        "    git-repository: https://github.com/example/repo\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)


def test_error_unknown_top_level_field(tmp_path):
    """An unrecognised top-level key raises WorkspaceConfigError."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\nunknown-field: oops\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)


def test_load_config_with_remote_sync_directory(tmp_path):
    """A config with remote-sync-directory is parsed correctly."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\nremote-sync-directory: .remotes\n",
        encoding="utf-8",
    )

    config = load_workspace_config(cfg_file)

    assert config.remote_sync_directory == ".remotes"


def test_load_config_default_remote_sync_directory(tmp_path):
    """When remote-sync-directory is absent, the default is '.archml-remotes'."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text("build-directory: build\n", encoding="utf-8")

    config = load_workspace_config(cfg_file)

    assert config.remote_sync_directory == ".archml-remotes"


def test_find_workspace_root_in_current_directory(tmp_path):
    """find_workspace_root returns the directory itself when it contains the workspace file."""
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: build\n", encoding="utf-8")

    result = find_workspace_root(tmp_path)

    assert result == tmp_path


def test_find_workspace_root_in_parent_directory(tmp_path):
    """find_workspace_root walks up and finds the workspace in a parent directory."""
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: build\n", encoding="utf-8")
    child_dir = tmp_path / "subdir" / "nested"
    child_dir.mkdir(parents=True)

    result = find_workspace_root(child_dir)

    assert result == tmp_path


def test_find_workspace_root_returns_none_when_not_found(tmp_path):
    """find_workspace_root returns None when no workspace file exists anywhere in the tree."""
    child_dir = tmp_path / "subdir"
    child_dir.mkdir()

    result = find_workspace_root(child_dir)

    assert result is None


def test_find_workspace_root_uses_nearest_ancestor(tmp_path):
    """find_workspace_root returns the closest (innermost) workspace directory."""
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: outer\n", encoding="utf-8")
    inner_dir = tmp_path / "inner"
    inner_dir.mkdir()
    (inner_dir / ".archml-workspace.yaml").write_text("build-directory: inner\n", encoding="utf-8")
    nested = inner_dir / "deep"
    nested.mkdir()

    result = find_workspace_root(nested)

    assert result == inner_dir


def test_find_workspace_root_returns_given_dir_when_it_is_the_root(tmp_path):
    """find_workspace_root resolves the start directory and finds the workspace in it."""
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: build\n", encoding="utf-8")

    result = find_workspace_root(tmp_path / ".")

    assert result == tmp_path
