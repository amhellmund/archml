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


def test_init_creates_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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


def test_init_default_directory_uses_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """init with no directory argument uses the current working directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["archml", "init"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    assert (tmp_path / ".archml-workspace").exists()


def test_init_fails_if_workspace_already_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """init exits with error code 1 when workspace already exists."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    monkeypatch.setattr(sys, "argv", ["archml", "init", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_init_fails_if_directory_does_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """init exits with error code 1 when target directory does not exist."""
    missing = tmp_path / "nonexistent"
    monkeypatch.setattr(sys, "argv", ["archml", "init", str(missing)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


# -------- check tests --------


def test_check_with_no_archml_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """check exits with code 0 and reports no files when workspace has none."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0


def test_check_with_archml_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """check discovers .archml files and reports checking them."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    (tmp_path / "arch.archml").write_text("# placeholder\n")
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "1" in captured.out
    assert "No issues found." in captured.out


def test_check_fails_if_no_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """check exits with error code 1 when no workspace file is found."""
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_check_fails_if_directory_does_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """check exits with error code 1 when directory does not exist."""
    missing = tmp_path / "nonexistent"
    monkeypatch.setattr(sys, "argv", ["archml", "check", str(missing)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


# -------- serve tests --------


def test_serve_fails_if_no_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """serve exits with error code 1 when no workspace file is found."""
    monkeypatch.setattr(sys, "argv", ["archml", "serve", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_serve_fails_if_directory_does_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    with patch("archml.webui.app.create_app", return_value=mock_app):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 0
    mock_app.run.assert_called_once_with(host="127.0.0.1", port=8050, debug=False)


def test_serve_custom_host_and_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """serve passes custom host and port to the app."""
    (tmp_path / ".archml-workspace").write_text("[workspace]\nversion = '1'\n")
    monkeypatch.setattr(
        sys,
        "argv",
        ["archml", "serve", "--host", "0.0.0.0", "--port", "9000", str(tmp_path)],
    )
    mock_app = MagicMock()
    with patch("archml.webui.app.create_app", return_value=mock_app):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 0
    mock_app.run.assert_called_once_with(host="0.0.0.0", port=9000, debug=False)
