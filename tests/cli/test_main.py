# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ArchML CLI entry point."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from archml.cli.main import main

# ###############
# Public Interface
# ###############


def test_main_no_args_prints_help_and_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() with no subcommand prints help and exits with code 0."""
    monkeypatch.setattr(sys, "argv", ["archml"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0


# -------- init tests --------


def test_init_creates_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """init creates .archml-workspace file in the specified directory."""
    monkeypatch.setattr(sys, "argv", ["archml", "init", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    workspace_file = tmp_path / ".archml-workspace"
    assert workspace_file.exists()
    content = workspace_file.read_text()
    assert "[workspace]" in content
    assert 'version = "1"' in content


def test_init_default_directory_uses_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """init with no directory argument uses the current working directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["archml", "init"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    assert (tmp_path / ".archml-workspace").exists()


def test_init_fails_if_workspace_already_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """init exits with error code 1 when workspace already exists."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    monkeypatch.setattr(sys, "argv", ["archml", "init", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_init_fails_if_directory_does_not_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """init exits with error code 1 when target directory does not exist."""
    missing = tmp_path / "nonexistent"
    monkeypatch.setattr(sys, "argv", ["archml", "init", str(missing)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


# -------- check tests --------


def test_check_with_no_archml_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """check exits with code 0 and reports no files when workspace has none."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0


def test_check_with_valid_archml_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """check discovers .archml files, compiles them, and reports success."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / "arch.archml").write_text("component MyComponent {}\n")
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "1" in captured.out
    assert "No issues found." in captured.out


def test_check_reports_compile_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """check exits with code 1 when a .archml file has a parse error."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / "bad.archml").write_text("component {}")  # missing name
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error" in captured.err


def test_check_reports_validation_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """check exits with code 1 when business validation finds errors."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    # Connection cycle: A -> B -> A (inline components inside system)
    (tmp_path / "cycle.archml").write_text(
        "interface I { field v: Int }\n"
        "system S {\n"
        "  component A { provides I requires I }\n"
        "  component B { provides I requires I }\n"
        "  connect A -> B by I\n"
        "  connect B -> A by I\n"
        "}\n"
    )
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_check_reports_validation_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """check exits with code 0 but prints warnings for isolated components."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    # An isolated component triggers a warning but not an error.
    (tmp_path / "isolated.archml").write_text("component Isolated {}\n")
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Warning" in captured.out


def test_check_uses_workspace_yaml_build_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """check uses the build-directory from .archml-workspace.yaml when present."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: custom-build\n")
    (tmp_path / "arch.archml").write_text("interface Signal { field v: Int }\ncomponent A { provides Signal }\n")
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    assert (tmp_path / "custom-build").exists()


def test_check_invalid_workspace_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """check exits with code 1 when .archml-workspace.yaml is invalid."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text("bad yaml: [unterminated\n")
    (tmp_path / "arch.archml").write_text("component A {}\n")
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error" in captured.err


def test_check_fails_if_no_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """check exits with error code 1 when no workspace file is found."""
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_check_fails_if_directory_does_not_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """check exits with error code 1 when directory does not exist."""
    missing = tmp_path / "nonexistent"
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(missing)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_check_reports_parse_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """check exits with code 1 and prints error message on parse failure."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / "bad.archml").write_text("component {}\n")  # missing name
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error" in captured.err


def test_check_with_workspace_yaml_and_local_source_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """check resolves mnemonic imports from the workspace YAML source-imports."""
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    (lib_dir / "iface.archml").write_text("interface MyIface { field v: Int }\n")

    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text(
        "build-directory: build\nsource-imports:\n  - name: mylib\n    local-path: lib\n"
    )
    (tmp_path / "app.archml").write_text("from mylib/iface import MyIface\ncomponent C { requires MyIface }\n")

    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "No issues found." in captured.out


def test_check_with_workspace_yaml_invalid_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """check exits with code 1 when .archml-workspace.yaml is invalid."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text("invalid: yaml: [broken\n")
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error" in captured.err


def test_check_excludes_build_directory_from_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Artifacts in the build directory are not re-scanned as source files."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: build\n")

    # Place a valid source file and compile it once to create the artifact.
    (tmp_path / "comp.archml").write_text("component Good {}\n")
    # Also create a broken .archml inside the build directory (should be ignored).
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    (build_dir / "fake.archml").write_text("component {}\n")  # invalid — missing name

    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "No issues found." in captured.out


# -------- serve tests --------


def test_serve_fails_if_no_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """serve exits with error code 1 when no workspace file is found."""
    monkeypatch.setattr(sys, "argv", ["archml", "serve", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_serve_fails_if_directory_does_not_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """serve exits with error code 1 when directory does not exist."""
    missing = tmp_path / "nonexistent"
    monkeypatch.setattr(sys, "argv", ["archml", "serve", str(missing)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_serve_launches_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """serve creates and runs the web app when workspace exists."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    monkeypatch.setattr(sys, "argv", ["archml", "serve", str(tmp_path)])
    mock_app = MagicMock()
    with (
        patch("archml.webui.app.create_app", return_value=mock_app),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 0
    mock_app.run.assert_called_once_with(host="127.0.0.1", port=8050, debug=False)


def test_serve_custom_host_and_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """serve passes custom host and port to the app."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    monkeypatch.setattr(
        sys,
        "argv",
        ["archml", "serve", "--host", "0.0.0.0", "--port", "9000", str(tmp_path)],
    )
    mock_app = MagicMock()
    with (
        patch("archml.webui.app.create_app", return_value=mock_app),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 0
    mock_app.run.assert_called_once_with(host="0.0.0.0", port=9000, debug=False)


# -------- sync-remote tests --------

_COMMIT_40 = "a" * 40


def test_sync_remote_fails_if_no_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync-remote exits with code 1 when no workspace file is found."""
    monkeypatch.setattr(sys, "argv", ["archml", "sync-remote", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_sync_remote_fails_if_directory_does_not_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync-remote exits with code 1 when directory does not exist."""
    missing = tmp_path / "nonexistent"
    monkeypatch.setattr(sys, "argv", ["archml", "sync-remote", str(missing)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_sync_remote_no_workspace_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync-remote exits 0 with a message when no workspace YAML is present."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    monkeypatch.setattr(sys, "argv", ["archml", "sync-remote", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0


def test_sync_remote_no_git_imports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync-remote exits 0 when no git imports are configured."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: build\n")
    monkeypatch.setattr(sys, "argv", ["archml", "sync-remote", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0


def test_sync_remote_fails_without_lockfile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """sync-remote exits 1 when the lockfile is missing."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: payments\n"
        "    git-repository: https://example.com/payments\n"
        "    revision: main\n"
    )
    monkeypatch.setattr(sys, "argv", ["archml", "sync-remote", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_sync_remote_fails_if_repo_not_in_lockfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """sync-remote exits 1 when a configured repo is missing from the lockfile."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: payments\n"
        "    git-repository: https://example.com/payments\n"
        "    revision: main\n"
    )
    (tmp_path / ".archml-lockfile.yaml").write_text("locked-revisions: []\n")
    monkeypatch.setattr(sys, "argv", ["archml", "sync-remote", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "not in the lockfile" in captured.err


def test_sync_remote_skips_repo_already_at_pinned_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """sync-remote skips a repo that is already at the pinned commit."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: payments\n"
        "    git-repository: https://example.com/payments\n"
        "    revision: main\n"
    )
    (tmp_path / ".archml-lockfile.yaml").write_text(
        f"locked-revisions:\n"
        f"  - name: payments\n"
        f"    git-repository: https://example.com/payments\n"
        f"    revision: main\n"
        f"    commit: {_COMMIT_40}\n"
    )
    monkeypatch.setattr(sys, "argv", ["archml", "sync-remote", str(tmp_path)])
    with (
        patch("archml.workspace.git_ops.get_current_commit", return_value=_COMMIT_40),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "already at" in captured.out


def test_sync_remote_clones_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """sync-remote calls clone_at_commit when repo is not at the pinned commit."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: payments\n"
        "    git-repository: https://example.com/payments\n"
        "    revision: main\n"
    )
    (tmp_path / ".archml-lockfile.yaml").write_text(
        f"locked-revisions:\n"
        f"  - name: payments\n"
        f"    git-repository: https://example.com/payments\n"
        f"    revision: main\n"
        f"    commit: {_COMMIT_40}\n"
    )
    monkeypatch.setattr(sys, "argv", ["archml", "sync-remote", str(tmp_path)])
    with (
        patch("archml.workspace.git_ops.get_current_commit", return_value=None),
        patch("archml.workspace.git_ops.clone_at_commit") as mock_clone,
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 0
    mock_clone.assert_called_once_with(
        "https://example.com/payments",
        _COMMIT_40,
        tmp_path / ".archml-remotes" / "payments",
    )


def test_sync_remote_reports_error_on_clone_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """sync-remote exits 1 and reports an error if clone_at_commit fails."""
    from archml.workspace.git_ops import GitError

    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: payments\n"
        "    git-repository: https://example.com/payments\n"
        "    revision: main\n"
    )
    (tmp_path / ".archml-lockfile.yaml").write_text(
        f"locked-revisions:\n"
        f"  - name: payments\n"
        f"    git-repository: https://example.com/payments\n"
        f"    revision: main\n"
        f"    commit: {_COMMIT_40}\n"
    )
    monkeypatch.setattr(sys, "argv", ["archml", "sync-remote", str(tmp_path)])
    with (
        patch("archml.workspace.git_ops.get_current_commit", return_value=None),
        patch("archml.workspace.git_ops.clone_at_commit", side_effect=GitError("network error")),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error" in captured.err


def test_sync_remote_uses_custom_sync_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sync-remote uses the remote-sync-directory from workspace config."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text(
        "build-directory: build\n"
        "remote-sync-directory: custom-remotes\n"
        "source-imports:\n"
        "  - name: lib\n"
        "    git-repository: https://example.com/lib\n"
        "    revision: main\n"
    )
    (tmp_path / ".archml-lockfile.yaml").write_text(
        f"locked-revisions:\n"
        f"  - name: lib\n"
        f"    git-repository: https://example.com/lib\n"
        f"    revision: main\n"
        f"    commit: {_COMMIT_40}\n"
    )
    monkeypatch.setattr(sys, "argv", ["archml", "sync-remote", str(tmp_path)])
    with (
        patch("archml.workspace.git_ops.get_current_commit", return_value=None),
        patch("archml.workspace.git_ops.clone_at_commit") as mock_clone,
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 0
    mock_clone.assert_called_once_with(
        "https://example.com/lib",
        _COMMIT_40,
        tmp_path / "custom-remotes" / "lib",
    )


# -------- update-remote tests --------


def test_update_remote_fails_if_no_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """update-remote exits with code 1 when no workspace file is found."""
    monkeypatch.setattr(sys, "argv", ["archml", "update-remote", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_update_remote_fails_if_directory_does_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """update-remote exits with code 1 when directory does not exist."""
    missing = tmp_path / "nonexistent"
    monkeypatch.setattr(sys, "argv", ["archml", "update-remote", str(missing)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_update_remote_no_workspace_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """update-remote exits 0 with a message when no workspace YAML is present."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    monkeypatch.setattr(sys, "argv", ["archml", "update-remote", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0


def test_update_remote_no_git_imports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """update-remote exits 0 when no git imports are configured."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: build\n")
    monkeypatch.setattr(sys, "argv", ["archml", "update-remote", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0


def test_update_remote_creates_lockfile_from_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """update-remote creates a lockfile by resolving branch revisions."""
    resolved_commit = "c" * 40
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: payments\n"
        "    git-repository: https://example.com/payments\n"
        "    revision: main\n"
    )
    monkeypatch.setattr(sys, "argv", ["archml", "update-remote", str(tmp_path)])
    with (
        patch("archml.workspace.git_ops.resolve_commit", return_value=resolved_commit),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 0
    lockfile_path = tmp_path / ".archml-lockfile.yaml"
    assert lockfile_path.exists()

    from archml.workspace.lockfile import load_lockfile

    lockfile = load_lockfile(lockfile_path)
    assert len(lockfile.locked_revisions) == 1
    assert lockfile.locked_revisions[0].name == "payments"
    assert lockfile.locked_revisions[0].commit == resolved_commit
    assert lockfile.locked_revisions[0].revision == "main"


def test_update_remote_pins_commit_hash_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """update-remote does not call git for revisions that are already commit hashes."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: lib\n"
        "    git-repository: https://example.com/lib\n"
        f"    revision: {_COMMIT_40}\n"
    )
    monkeypatch.setattr(sys, "argv", ["archml", "update-remote", str(tmp_path)])
    with (
        patch("archml.workspace.git_ops.resolve_commit") as mock_resolve,
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 0
    mock_resolve.assert_not_called()

    from archml.workspace.lockfile import load_lockfile

    lockfile = load_lockfile(tmp_path / ".archml-lockfile.yaml")
    assert lockfile.locked_revisions[0].commit == _COMMIT_40


def test_update_remote_updates_existing_lockfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """update-remote updates an existing lockfile with new commits."""
    old_commit = "0" * 40
    new_commit = "1" * 40
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: payments\n"
        "    git-repository: https://example.com/payments\n"
        "    revision: main\n"
    )
    (tmp_path / ".archml-lockfile.yaml").write_text(
        f"locked-revisions:\n"
        f"  - name: payments\n"
        f"    git-repository: https://example.com/payments\n"
        f"    revision: main\n"
        f"    commit: {old_commit}\n"
    )
    monkeypatch.setattr(sys, "argv", ["archml", "update-remote", str(tmp_path)])
    with (
        patch("archml.workspace.git_ops.resolve_commit", return_value=new_commit),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 0

    from archml.workspace.lockfile import load_lockfile

    lockfile = load_lockfile(tmp_path / ".archml-lockfile.yaml")
    assert lockfile.locked_revisions[0].commit == new_commit


def test_update_remote_exits_1_on_resolution_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """update-remote exits 1 if a revision cannot be resolved."""
    from archml.workspace.git_ops import GitError

    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: lib\n"
        "    git-repository: https://example.com/lib\n"
        "    revision: nonexistent-branch\n"
    )
    monkeypatch.setattr(sys, "argv", ["archml", "update-remote", str(tmp_path)])
    with (
        patch("archml.workspace.git_ops.resolve_commit", side_effect=GitError("not found")),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error" in captured.err


def test_check_command_uses_synced_remote_repos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """check includes synced remote repos in the source import map when they exist."""
    remote_dir = tmp_path / ".archml-remotes" / "payments"
    remote_dir.mkdir(parents=True)
    (remote_dir / "api.archml").write_text("interface PaymentAPI { field amount: Decimal }\n")

    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: payments\n"
        "    git-repository: https://example.com/payments\n"
        "    revision: main\n"
    )
    (tmp_path / "app.archml").write_text(
        "from @payments/api import PaymentAPI\ncomponent C { requires PaymentAPI }\n"
    )
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "No issues found." in captured.out


def test_check_command_loads_remote_repo_mnemonics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """check exposes @repo/mnemonic keys from the remote repo's workspace config."""
    remote_dir = tmp_path / ".archml-remotes" / "payments"
    remote_lib_dir = remote_dir / "src" / "lib"
    remote_lib_dir.mkdir(parents=True)
    (remote_lib_dir / "types.archml").write_text("interface PaymentType { field amount: Decimal }\n")

    # Remote repo has its own .archml-workspace.yaml defining a "lib" mnemonic.
    (remote_dir / ".archml-workspace.yaml").write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: lib\n"
        "    local-path: src/lib\n"
    )

    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: payments\n"
        "    git-repository: https://example.com/payments\n"
        "    revision: main\n"
    )
    # Import using the remote mnemonic: @payments/lib/types
    (tmp_path / "app.archml").write_text(
        "from @payments/lib/types import PaymentType\ncomponent C { requires PaymentType }\n"
    )
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "No issues found." in captured.out


def test_check_command_warns_on_invalid_remote_workspace_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """check emits a warning when a remote repo's .archml-workspace.yaml is invalid."""
    remote_dir = tmp_path / ".archml-remotes" / "payments"
    remote_dir.mkdir(parents=True)
    (remote_dir / "api.archml").write_text("interface PaymentAPI { field amount: Decimal }\n")
    # Malformed remote workspace config
    (remote_dir / ".archml-workspace.yaml").write_text("bad yaml: [unterminated\n")

    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / ".archml-workspace.yaml").write_text(
        "build-directory: build\n"
        "source-imports:\n"
        "  - name: payments\n"
        "    git-repository: https://example.com/payments\n"
        "    revision: main\n"
    )
    (tmp_path / "app.archml").write_text(
        "from @payments/api import PaymentAPI\ncomponent C { requires PaymentAPI }\n"
    )
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    # Still succeeds: invalid remote config just produces a warning, not a hard error.
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Warning" in captured.out
    assert "No issues found." in captured.out
