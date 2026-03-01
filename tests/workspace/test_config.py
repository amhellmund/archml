# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the workspace configuration module."""

import pytest

from archml.workspace.config import (
    GitPathImport,
    LocalPathImport,
    WorkspaceConfig,
    WorkspaceConfigError,
    load_workspace_config,
)

# ###############
# Public Interface
# ###############


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
    cfg_file.write_text(
        "source-imports:\n  - name: src\n    local-path: .\n",
        encoding="utf-8",
    )

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
        "build-directory: build\n"
        "source-imports:\n  - name: src\n    local-path: .\n"
        "unknown-field: oops\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)


def test_load_config_with_remote_sync_directory(tmp_path):
    """A config with remote-sync-directory is parsed correctly."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\n"
        "remote-sync-directory: .remotes\n"
        "source-imports:\n  - name: src\n    local-path: .\n",
        encoding="utf-8",
    )

    config = load_workspace_config(cfg_file)

    assert config.remote_sync_directory == ".remotes"


def test_load_config_default_remote_sync_directory(tmp_path):
    """When remote-sync-directory is absent, the default is '.archml-remotes'."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\nsource-imports:\n  - name: src\n    local-path: .\n",
        encoding="utf-8",
    )

    config = load_workspace_config(cfg_file)

    assert config.remote_sync_directory == ".archml-remotes"


# ###############
# Mnemonic name validation
# ###############


def test_error_mnemonic_missing_source_imports(tmp_path):
    """Omitting source-imports entirely raises WorkspaceConfigError."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text("build-directory: build\n", encoding="utf-8")

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)


def test_error_empty_source_imports_list(tmp_path):
    """An empty source-imports list raises WorkspaceConfigError (at least one required)."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\nsource-imports: []\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)


def test_error_mnemonic_name_with_uppercase(tmp_path):
    """A mnemonic name with uppercase letters raises WorkspaceConfigError."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\nsource-imports:\n  - name: MyLib\n    local-path: .\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)


def test_error_mnemonic_name_starts_with_digit(tmp_path):
    """A mnemonic name starting with a digit raises WorkspaceConfigError."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\nsource-imports:\n  - name: 1lib\n    local-path: .\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)


def test_error_mnemonic_name_with_slash(tmp_path):
    """A mnemonic name containing a slash raises WorkspaceConfigError."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\nsource-imports:\n  - name: my/lib\n    local-path: .\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)


def test_error_mnemonic_name_with_space(tmp_path):
    """A mnemonic name containing a space raises WorkspaceConfigError."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\nsource-imports:\n  - name: my lib\n    local-path: .\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)


def test_error_mnemonic_name_starts_with_dash(tmp_path):
    """A mnemonic name starting with a dash raises WorkspaceConfigError."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\nsource-imports:\n  - name: -mylib\n    local-path: .\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)


def test_valid_mnemonic_names(tmp_path):
    """Valid mnemonic names using letters, digits, dashes, and underscores are accepted."""
    valid_names = ["src", "mylib", "my-lib", "my-lib-2", "a", "lib123", "my_lib"]
    for name in valid_names:
        cfg_file = tmp_path / f".archml-workspace-{name}.yaml"
        cfg_file.write_text(
            f"build-directory: build\nsource-imports:\n  - name: {name}\n    local-path: .\n",
            encoding="utf-8",
        )
        config = load_workspace_config(cfg_file)
        assert config.source_imports[0].name == name


def test_error_git_repo_name_with_slash(tmp_path):
    """A git repo name containing a slash raises WorkspaceConfigError."""
    cfg_file = tmp_path / ".archml-workspace.yaml"
    cfg_file.write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: my/repo\n"
        "    git-repository: https://github.com/example/repo\n"
        "    revision: main\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceConfigError, match="Invalid workspace config"):
        load_workspace_config(cfg_file)
