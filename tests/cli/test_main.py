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


def test_init_creates_workspace_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """init creates .archml-workspace.yaml in the specified directory."""
    monkeypatch.setattr(sys, "argv", ["archml", "init", "myrepo", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    assert (tmp_path / ".archml-workspace.yaml").exists()


def test_init_workspace_yaml_has_correct_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """init writes source-import mapping with the given mnemonic into the YAML config."""
    monkeypatch.setattr(sys, "argv", ["archml", "init", "myrepo", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    content = (tmp_path / ".archml-workspace.yaml").read_text()
    assert "name: myrepo" in content
    assert "local-path: ." in content
    assert "build-directory:" in content


def test_init_creates_workspace_dir_if_not_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """init creates the workspace directory when it does not yet exist."""
    new_dir = tmp_path / "new_workspace"
    assert not new_dir.exists()
    monkeypatch.setattr(sys, "argv", ["archml", "init", "myrepo", str(new_dir)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    assert new_dir.exists()
    assert (new_dir / ".archml-workspace.yaml").exists()


def test_init_fails_if_workspace_yaml_already_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """init exits with error code 1 when .archml-workspace.yaml already exists."""
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: .archml-build\n")
    monkeypatch.setattr(sys, "argv", ["archml", "init", "myrepo", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_init_fails_if_name_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """init exits with error code 1 when the mnemonic name is an empty string."""
    monkeypatch.setattr(sys, "argv", ["archml", "init", "", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_init_succeeds_if_dir_exists_without_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """init succeeds when the directory exists but has no .archml-workspace.yaml."""
    monkeypatch.setattr(sys, "argv", ["archml", "init", "myrepo", str(tmp_path)])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0


# -------- check tests --------


def test_check_with_no_archml_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """check exits with code 0 and reports no files when workspace has none."""
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: .archml-build\n")
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
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: .archml-build\n")
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
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: .archml-build\n")
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
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: .archml-build\n")
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
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: .archml-build\n")
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
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: .archml-build\n")
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
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: .archml-build\n")
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
    (tmp_path / ".archml-workspace.yaml").write_text("build-directory: .archml-build\n")
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
