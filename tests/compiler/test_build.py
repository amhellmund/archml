# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ArchML incremental compiler workflow."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from archml.compiler.artifact import ARTIFACT_SUFFIX, read_artifact
from archml.compiler.build import CompilerError, compile_files

# ###############
# Test data directory
# ###############

DATA_DIR = Path(__file__).parent.parent / "data" / "positive" / "compiler"

# ###############
# Helpers
# ###############


def _write(path: Path, content: str, *, mtime_offset: float = -2.0) -> None:
    """Write *content* to *path*, creating parent directories as needed.

    Sets the file's mtime to *mtime_offset* seconds relative to now (default:
    2 seconds in the past) so that subsequently written artifacts are reliably
    newer regardless of filesystem timestamp resolution.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    t = time.time() + mtime_offset
    os.utime(path, (t, t))


def _artifact(build_dir: Path, key: str) -> Path:
    """Return the expected artifact path for a canonical key."""
    parts = key.split("/")
    artifact_dir = build_dir
    for part in parts[:-1]:
        artifact_dir = artifact_dir / part
    return artifact_dir / (parts[-1] + ARTIFACT_SUFFIX)


# ###############
# Single-file compilation
# ###############


class TestSingleFile:
    def test_compiles_simple_file(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(
            src / "simple.farchml",
            """
interface Signal { v: Int }
component A { provides Signal }
""",
        )
        result = compile_files([src / "simple.farchml"], build, {("", "app"): src})
        assert "app/simple" in result
        assert result["app/simple"].components[0].name == "A"

    def test_artifact_written_to_build_dir(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        source = src / "x.farchml"
        _write(source, "component C {}")
        compile_files([source], build, {("", "app"): src})
        artifact = _artifact(build, "app/x")
        assert artifact.exists()

    def test_artifact_can_be_read_back(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        source = src / "x.farchml"
        _write(source, "component MyComp {}")
        compile_files([source], build, {("", "app"): src})
        artifact = _artifact(build, "app/x")
        af = read_artifact(artifact)
        assert af.components[0].name == "MyComp"

    def test_compiles_file_with_enum_and_type(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(
            src / "types.farchml",
            """
enum Color {
    Red
    Green
    Blue
}
type Point { x: Int y: Int }
""",
        )
        result = compile_files([src / "types.farchml"], build, {("", "app"): src})
        af = result["app/types"]
        assert af.enums[0].name == "Color"
        assert af.types[0].name == "Point"


# ###############
# Cache behaviour
# ###############


class TestCache:
    def test_cache_hit_skips_recompile(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        source = src / "x.farchml"
        _write(source, "component A {}")  # mtime set 2s in the past

        compile_files([source], build, {("", "app"): src})
        artifact = _artifact(build, "app/x")
        mtime_first = artifact.stat().st_mtime

        compile_files([source], build, {("", "app"): src})
        mtime_second = artifact.stat().st_mtime

        assert mtime_first == mtime_second  # artifact was NOT rewritten

    def test_stale_artifact_triggers_recompile(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        source = src / "x.farchml"
        _write(source, "component A {}")  # mtime 2s in the past

        compile_files([source], build, {("", "app"): src})
        artifact = _artifact(build, "app/x")
        content_first = artifact.read_text(encoding="utf-8")

        # Touch the source file to make it newer than the artifact.
        _write(source, "component B {}", mtime_offset=2.0)  # mtime = 2s in the future

        compile_files([source], build, {("", "app"): src})
        content_second = artifact.read_text(encoding="utf-8")

        assert content_second != content_first  # artifact was rewritten with new content

    def test_stale_artifact_reads_updated_content(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        source = src / "x.farchml"
        _write(source, "component A {}", mtime_offset=-2.0)

        compile_files([source], build, {("", "app"): src})

        _write(source, "component NewComp {}", mtime_offset=2.0)  # 2s in future = newer than artifact
        result = compile_files([source], build, {("", "app"): src})

        assert result["app/x"].components[0].name == "NewComp"


# ###############
# Multi-file compilation
# ###############


class TestMultiFile:
    def test_compiles_file_with_dependency(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(
            src / "types.farchml",
            "interface Signal { v: Int }",
        )
        _write(
            src / "app.farchml",
            """
from app/types import Signal
component Worker { requires Signal }
""",
        )
        result = compile_files([src / "app.farchml"], build, {("", "app"): src})
        assert "app/app" in result
        assert "app/types" in result

    def test_dependency_artifact_also_written(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "types.farchml", "interface Signal { v: Int }")
        _write(src / "app.farchml", "from app/types import Signal\ncomponent W { requires Signal }")
        compile_files([src / "app.farchml"], build, {("", "app"): src})
        types_artifact = _artifact(build, "app/types")
        assert types_artifact.exists()

    def test_three_level_dependency_chain(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "base.farchml", "interface IBase { x: Int }")
        _write(src / "mid.farchml", "from app/base import IBase\ncomponent Mid { requires IBase }")
        _write(
            src / "top.farchml", "from app/base import IBase\nfrom app/mid import Mid\ncomponent Top { requires IBase }"
        )
        result = compile_files([src / "top.farchml"], build, {("", "app"): src})
        assert "app/base" in result
        assert "app/mid" in result
        assert "app/top" in result

    def test_shared_dependency_compiled_once(self, tmp_path: Path) -> None:
        """Two top-level files sharing a dependency don't recompile it."""
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "shared.farchml", "interface I { v: Int }")
        _write(src / "a.farchml", "from app/shared import I\ncomponent A { requires I }")
        _write(src / "b.farchml", "from app/shared import I\ncomponent B { requires I }")
        result = compile_files([src / "a.farchml", src / "b.farchml"], build, {("", "app"): src})
        assert "app/shared" in result
        assert "app/a" in result
        assert "app/b" in result

    def test_subdirectory_dependency(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "shared" / "types.farchml", "interface Signal { v: Int }")
        _write(
            src / "worker.farchml",
            "from app/shared/types import Signal\ncomponent Worker { requires Signal }",
        )
        result = compile_files([src / "worker.farchml"], build, {("", "app"): src})
        assert "app/worker" in result
        assert "app/shared/types" in result

    def test_compiled_from_test_data(self, tmp_path: Path) -> None:
        """Compile the realistic multi-file test data under tests/data/positive/compiler/."""
        result = compile_files(
            [DATA_DIR / "main.farchml"],
            tmp_path / "build",
            {("", "compiler"): DATA_DIR},
        )
        assert "compiler/main" in result
        assert "compiler/worker" in result
        assert "compiler/shared/types" in result


# ###############
# Source import resolution
# ###############


class TestSourceImports:
    def test_resolves_mnemonic_import(self, tmp_path: Path) -> None:
        """Files imported via mnemonic/path are resolved from the mnemonic base."""
        src = tmp_path / "src"
        lib = tmp_path / "lib"
        build = tmp_path / "build"

        _write(lib / "types.farchml", "interface Signal { v: Int }")
        _write(
            src / "app.farchml",
            "from mylib/types import Signal\ncomponent Worker { requires Signal }",
        )

        result = compile_files(
            [src / "app.farchml"],
            build,
            {("", "app"): src, ("", "mylib"): lib},
        )
        assert "app/app" in result
        assert "mylib/types" in result

    def test_mnemonic_artifact_stored_under_mnemonic_prefix(self, tmp_path: Path) -> None:
        """Artifacts for mnemonic imports are stored under mnemonic/ in the build dir."""
        src = tmp_path / "src"
        lib = tmp_path / "lib"
        build = tmp_path / "build"

        _write(lib / "types.farchml", "interface Signal { v: Int }")
        _write(src / "app.farchml", "from mylib/types import Signal\ncomponent C { requires Signal }")

        compile_files([src / "app.farchml"], build, {("", "app"): src, ("", "mylib"): lib})

        assert _artifact(build, "mylib/types").exists()

    def test_mnemonic_import_in_subdirectory(self, tmp_path: Path) -> None:
        """Mnemonic imports work for files nested in subdirectories."""
        src = tmp_path / "src"
        lib = tmp_path / "lib"
        build = tmp_path / "build"

        _write(lib / "shared" / "base.farchml", "interface IBase { x: Int }")
        _write(
            src / "app.farchml",
            "from mylib/shared/base import IBase\ncomponent C { requires IBase }",
        )

        result = compile_files(
            [src / "app.farchml"],
            build,
            {("", "app"): src, ("", "mylib"): lib},
        )
        assert "mylib/shared/base" in result

    def test_multiple_mnemonics(self, tmp_path: Path) -> None:
        """Multiple mnemonic mappings can be used simultaneously."""
        src = tmp_path / "src"
        lib_a = tmp_path / "lib_a"
        lib_b = tmp_path / "lib_b"
        build = tmp_path / "build"

        _write(lib_a / "types.farchml", "interface TypeA { x: Int }")
        _write(lib_b / "types.farchml", "interface TypeB { y: Int }")
        _write(
            src / "app.farchml",
            "from liba/types import TypeA\nfrom libb/types import TypeB\n"
            "component C { requires TypeA\n requires TypeB }",
        )

        result = compile_files(
            [src / "app.farchml"],
            build,
            {("", "app"): src, ("", "liba"): lib_a, ("", "libb"): lib_b},
        )
        assert "liba/types" in result
        assert "libb/types" in result

    def test_mnemonic_dependency_compiled_transitively(self, tmp_path: Path) -> None:
        """A local file that imports from a mnemonic is compiled correctly."""
        src = tmp_path / "src"
        lib = tmp_path / "lib"
        build = tmp_path / "build"

        _write(lib / "iface.farchml", "interface IFace { v: Int }")
        _write(src / "mid.farchml", "from ext/iface import IFace\ncomponent Mid { requires IFace }")
        _write(src / "top.farchml", "from app/mid import Mid\ncomponent Top {}")

        result = compile_files(
            [src / "top.farchml"],
            build,
            {("", "app"): src, ("", "ext"): lib},
        )
        assert "app/top" in result
        assert "app/mid" in result
        assert "ext/iface" in result

    def test_remote_git_import_raises_if_mnemonic_not_in_source_import_map(self, tmp_path: Path) -> None:
        """Importing via @repo/mnemonic/path raises CompilerError when the mnemonic is absent."""
        src = tmp_path / "src"
        build = tmp_path / "build"

        _write(src / "app.farchml", "from @myrepo/mylib/types import X\ncomponent C {}")

        with pytest.raises(CompilerError, match="not found in workspace"):
            compile_files([src / "app.farchml"], build, {("", "app"): src})

    def test_remote_git_import_resolves_from_source_import_map(self, tmp_path: Path) -> None:
        """Files imported via @repo/mnemonic/path resolve when the mnemonic key is present."""
        src = tmp_path / "src"
        remote_services = tmp_path / "remote" / "services"
        build = tmp_path / "build"

        _write(remote_services / "payment.farchml", "interface PaymentService { amount: Float }")
        _write(
            src / "app.farchml",
            "from @payments/services/payment import PaymentService\ncomponent C { requires PaymentService }",
        )

        result = compile_files(
            [src / "app.farchml"],
            build,
            {("", "app"): src, ("@payments", "services"): remote_services},
        )

        assert "app/app" in result
        assert "@payments/services/payment" in result

    def test_remote_git_import_artifact_stored_under_at_prefix(self, tmp_path: Path) -> None:
        """Artifacts for remote git imports are stored under @repo/mnemonic/ in the build dir."""
        src = tmp_path / "src"
        remote_api = tmp_path / "remote" / "api"
        build = tmp_path / "build"

        _write(remote_api / "types.farchml", "interface RemoteType { v: Int }")
        _write(src / "app.farchml", "from @ext/api/types import RemoteType\ncomponent C { requires RemoteType }")

        compile_files([src / "app.farchml"], build, {("", "app"): src, ("@ext", "api"): remote_api})

        assert _artifact(build, "@ext/api/types").exists()

    def test_remote_git_import_with_mnemonic_resolves_via_mnemonic_key(self, tmp_path: Path) -> None:
        """@repo/mnemonic/path imports resolve via (repo, mnemonic) key in source_import_map."""
        src = tmp_path / "src"
        remote_utils = tmp_path / "remote" / "utils"
        build = tmp_path / "build"

        _write(remote_utils / "helpers.farchml", "interface Helper { v: Int }")
        _write(
            src / "app.farchml",
            "from @payments/utils/helpers import Helper\ncomponent C { requires Helper }",
        )

        result = compile_files(
            [src / "app.farchml"],
            build,
            {("", "app"): src, ("@payments", "utils"): remote_utils},
        )

        assert "app/app" in result
        assert "@payments/utils/helpers" in result

    def test_remote_git_import_raises_when_mnemonic_not_configured(self, tmp_path: Path) -> None:
        """@repo/mnemonic/path raises CompilerError when the mnemonic is not in the map."""
        src = tmp_path / "src"
        build = tmp_path / "build"

        _write(
            src / "app.farchml",
            "from @ext/lib/types import T\ncomponent C { requires T }",
        )

        with pytest.raises(CompilerError, match="not found in workspace"):
            compile_files([src / "app.farchml"], build, {("", "app"): src})

    def test_mnemonic_missing_file_raises_compiler_error(self, tmp_path: Path) -> None:
        """A mnemonic import that refers to a non-existent file raises CompilerError."""
        src = tmp_path / "src"
        lib = tmp_path / "lib"
        build = tmp_path / "build"
        lib.mkdir()

        _write(src / "app.farchml", "from mylib/missing import X\ncomponent C {}")

        with pytest.raises(CompilerError, match="not found"):
            compile_files([src / "app.farchml"], build, {("", "app"): src, ("", "mylib"): lib})

    def test_mnemonic_based_import_resolves_correctly(self, tmp_path: Path) -> None:
        """compile_files resolves mnemonic-based imports from the source import map."""
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "x.farchml", "component C {}")

        result = compile_files([src / "x.farchml"], build, {("", "app"): src})
        assert "app/x" in result

    def test_mnemonic_cache_hit(self, tmp_path: Path) -> None:
        """A cached artifact for a mnemonic import is reused on subsequent builds."""
        src = tmp_path / "src"
        lib = tmp_path / "lib"
        build = tmp_path / "build"

        _write(lib / "types.farchml", "interface Signal { v: Int }")
        _write(src / "app.farchml", "from mylib/types import Signal\ncomponent W { requires Signal }")

        compile_files([src / "app.farchml"], build, {("", "app"): src, ("", "mylib"): lib})
        artifact = _artifact(build, "mylib/types")
        mtime_first = artifact.stat().st_mtime

        compile_files([src / "app.farchml"], build, {("", "app"): src, ("", "mylib"): lib})
        mtime_second = artifact.stat().st_mtime

        assert mtime_first == mtime_second

    def test_bare_import_without_mnemonic_raises_compiler_error(self, tmp_path: Path) -> None:
        """An import without a mnemonic prefix raises CompilerError."""
        src = tmp_path / "src"
        build = tmp_path / "build"

        _write(src / "app.farchml", "from types import Signal\ncomponent C {}")

        with pytest.raises(CompilerError, match="mnemonic/path"):
            compile_files([src / "app.farchml"], build, {("", "app"): src})

    def test_remote_import_without_path_raises_compiler_error(self, tmp_path: Path) -> None:
        """A remote import missing the path component raises CompilerError."""
        src = tmp_path / "src"
        build = tmp_path / "build"

        _write(src / "app.farchml", "from @repo/mnemonic import X\ncomponent C {}")

        with pytest.raises(CompilerError, match="missing path component"):
            compile_files([src / "app.farchml"], build, {("", "app"): src})

    def test_local_mnemonic_resolves_using_source_repo(self, tmp_path: Path) -> None:
        """Bare mnemonic imports resolve using the source file's repo context."""
        lib = tmp_path / "lib"
        build = tmp_path / "build"

        _write(lib / "utils.farchml", "interface IUtil { v: Int }")
        # lib/main.farchml imports from "lib" mnemonic (same repo "")
        _write(lib / "main.farchml", "from lib/utils import IUtil\ncomponent Main { requires IUtil }")

        result = compile_files(
            [lib / "main.farchml"],
            build,
            {("", "lib"): lib},
        )
        assert "lib/main" in result
        assert "lib/utils" in result


# ###############
# File-move recompilation
# ###############


class TestFileMoveRecompilation:
    def test_cache_busted_when_local_dep_is_moved(self, tmp_path: Path) -> None:
        """If a dependency file is moved, files that imported it are recompiled."""
        src = tmp_path / "src"
        build = tmp_path / "build"

        # Initial setup: app imports types from same mnemonic
        _write(src / "types.farchml", "interface Signal { v: Int }")
        _write(src / "app.farchml", "from app/types import Signal\ncomponent W { requires Signal }")

        compile_files([src / "app.farchml"], build, {("", "app"): src})
        app_artifact = _artifact(build, "app/app")
        mtime_before = app_artifact.stat().st_mtime

        # Simulate file being moved: delete 'types.farchml' (old location no longer exists)
        (src / "types.farchml").unlink()

        # Place the file at a new location and update app to import from new location
        _write(src / "signals" / "types.farchml", "interface Signal { v: Int }")
        _write(src / "app.farchml", "from app/signals/types import Signal\ncomponent W { requires Signal }")

        compile_files([src / "app.farchml"], build, {("", "app"): src})
        mtime_after = app_artifact.stat().st_mtime

        # app was recompiled because its source changed
        assert mtime_after != mtime_before
        assert "app/signals/types" in compile_files([src / "app.farchml"], build, {("", "app"): src})

    def test_cache_busted_when_mnemonic_dep_is_moved(self, tmp_path: Path) -> None:
        """Cache is invalidated when a mnemonic-based dependency no longer exists."""
        src = tmp_path / "src"
        lib = tmp_path / "lib"
        build = tmp_path / "build"

        # First compilation: mylib/types exists
        _write(lib / "types.farchml", "interface Signal { v: Int }")
        _write(src / "app.farchml", "from mylib/types import Signal\ncomponent W { requires Signal }")

        compile_files([src / "app.farchml"], build, {("", "app"): src, ("", "mylib"): lib})
        app_artifact = _artifact(build, "app/app")
        assert app_artifact.exists()

        # Simulate a move: the dependency at mylib/types is gone
        (lib / "types.farchml").unlink()
        # app.farchml is NOT updated yet — it still refers to the old path

        # Now trigger a recompile: since mylib/types is gone, the cache for
        # 'app' should be busted and re-parsing app should fail because the dep is missing.
        with pytest.raises(CompilerError, match="not found"):
            compile_files([src / "app.farchml"], build, {("", "app"): src, ("", "mylib"): lib})

    def test_up_to_date_cache_hit_survives_when_deps_still_exist(self, tmp_path: Path) -> None:
        """An up-to-date artifact is reused when all its imports still exist."""
        src = tmp_path / "src"
        lib = tmp_path / "lib"
        build = tmp_path / "build"

        _write(lib / "types.farchml", "interface Signal { v: Int }")
        _write(src / "app.farchml", "from mylib/types import Signal\ncomponent W { requires Signal }")

        compile_files([src / "app.farchml"], build, {("", "app"): src, ("", "mylib"): lib})
        app_artifact = _artifact(build, "app/app")
        mtime_before = app_artifact.stat().st_mtime

        # Second run: deps still exist, artifact is up-to-date → cache hit
        compile_files([src / "app.farchml"], build, {("", "app"): src, ("", "mylib"): lib})
        mtime_after = app_artifact.stat().st_mtime

        assert mtime_before == mtime_after


# ###############
# Error cases
# ###############


class TestErrorCases:
    def test_parse_error_raises_compiler_error(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "bad.farchml", "component {}")  # missing name
        with pytest.raises(CompilerError) as exc_info:
            compile_files([src / "bad.farchml"], build, {("", "app"): src})
        assert "bad.farchml" in str(exc_info.value)

    def test_lexer_error_raises_compiler_error(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "bad.farchml", "component C { ~ }")  # invalid character
        with pytest.raises(CompilerError) as exc_info:
            compile_files([src / "bad.farchml"], build, {("", "app"): src})
        assert "bad.farchml" in str(exc_info.value)

    def test_missing_dependency_raises_compiler_error(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "app.farchml", "from app/nonexistent import Something\ncomponent C {}")
        with pytest.raises(CompilerError, match="not found"):
            compile_files([src / "app.farchml"], build, {("", "app"): src})

    def test_semantic_error_raises_compiler_error(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(
            src / "bad.farchml",
            "component C { requires UnknownInterface }",
        )
        with pytest.raises(CompilerError) as exc_info:
            compile_files([src / "bad.farchml"], build, {("", "app"): src})
        assert "bad.farchml" in str(exc_info.value)

    def test_circular_dependency_raises_compiler_error(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        # a imports b, b imports a
        _write(src / "a.farchml", "from app/b import Something\ncomponent A {}")
        _write(src / "b.farchml", "from app/a import Something\ncomponent B {}")
        with pytest.raises(CompilerError, match="Circular dependency"):
            compile_files([src / "a.farchml"], build, {("", "app"): src})

    def test_compiler_error_message_includes_file_path(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "myfile.farchml", "component {}")
        with pytest.raises(CompilerError) as exc_info:
            compile_files([src / "myfile.farchml"], build, {("", "app"): src})
        assert "myfile" in str(exc_info.value)

    def test_multiple_semantic_errors_in_message(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(
            src / "bad.farchml",
            """
enum Dup {
    A
}
enum Dup {
    B
}
""",
        )
        with pytest.raises(CompilerError) as exc_info:
            compile_files([src / "bad.farchml"], build, {("", "app"): src})
        assert "bad.farchml" in str(exc_info.value)


# ###############
# Reserved file names
# ###############


class TestReservedFileNames:
    def test_file_named_after_keyword_raises_compiler_error(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "system.farchml", "component C {}")
        with pytest.raises(CompilerError, match="reserved"):
            compile_files([src / "system.farchml"], build, {("", "app"): src})

    def test_file_named_component_raises_compiler_error(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "component.farchml", "system S {}")
        with pytest.raises(CompilerError, match="reserved"):
            compile_files([src / "component.farchml"], build, {("", "app"): src})

    def test_file_named_type_raises_compiler_error(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "type.farchml", "enum E { A }")
        with pytest.raises(CompilerError, match="reserved"):
            compile_files([src / "type.farchml"], build, {("", "app"): src})

    def test_directory_segment_named_after_keyword_raises_compiler_error(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "interface" / "order.farchml", "component C {}")
        with pytest.raises(CompilerError, match="reserved"):
            compile_files([src / "interface" / "order.farchml"], build, {("", "app"): src})

    def test_non_reserved_file_name_is_accepted(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "order.farchml", "component C {}")
        result = compile_files([src / "order.farchml"], build, {("", "app"): src})
        assert "app/order" in result

    def test_error_message_includes_keyword(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "import.farchml", "component C {}")
        with pytest.raises(CompilerError) as exc_info:
            compile_files([src / "import.farchml"], build, {("", "app"): src})
        assert "'import'" in str(exc_info.value)
        assert "reserved" in str(exc_info.value)


# ###############
# Return value
# ###############


class TestReturnValue:
    def test_returns_empty_dict_for_no_files(self, tmp_path: Path) -> None:
        result = compile_files([], tmp_path / "build", {("", "app"): tmp_path / "src"})
        assert result == {}

    def test_key_uses_mnemonic_and_relative_path_without_extension(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "subdir" / "myfile.farchml", "component C {}")
        result = compile_files([src / "subdir" / "myfile.farchml"], build, {("", "app"): src})
        assert "app/subdir/myfile" in result

    def test_compiling_same_file_twice_returns_same_model(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "x.farchml", "component C {}")
        result = compile_files([src / "x.farchml", src / "x.farchml"], build, {("", "app"): src})
        assert len(result) == 1
        assert "app/x" in result

    def test_mnemonic_key_uses_mnemonic_prefix(self, tmp_path: Path) -> None:
        """Keys for mnemonic imports use mnemonic/path format."""
        src = tmp_path / "src"
        lib = tmp_path / "lib"
        build = tmp_path / "build"

        _write(lib / "iface.farchml", "interface I { v: Int }")
        _write(src / "app.farchml", "from ext/iface import I\ncomponent C { requires I }")

        result = compile_files([src / "app.farchml"], build, {("", "app"): src, ("", "ext"): lib})
        assert "ext/iface" in result


# ###############
# Parallel compilation
# ###############


class TestParallelCompilation:
    """compile_files processes independent files concurrently and respects
    topological ordering for files with dependencies."""

    def test_compiles_many_independent_files(self, tmp_path: Path) -> None:
        """Multiple independent files are all compiled and returned."""
        src = tmp_path / "src"
        build = tmp_path / "build"
        n = 8
        sources = []
        for i in range(n):
            f = src / f"comp{i}.farchml"
            _write(f, f"component C{i} {{}}")
            sources.append(f)

        result = compile_files(sources, build, {("", "app"): src})
        assert len(result) == n
        for i in range(n):
            key = f"app/comp{i}"
            assert key in result
            assert result[key].components[0].name == f"C{i}"

    def test_all_artifacts_written_for_independent_files(self, tmp_path: Path) -> None:
        """An artifact is written for every compiled file."""
        src = tmp_path / "src"
        build = tmp_path / "build"
        n = 6
        sources = []
        for i in range(n):
            f = src / f"file{i}.farchml"
            _write(f, f"interface I{i} {{ v: Int }}")
            sources.append(f)

        compile_files(sources, build, {("", "app"): src})
        for i in range(n):
            assert _artifact(build, f"app/file{i}").exists()

    def test_dependency_compiled_once_when_shared_by_multiple_files(self, tmp_path: Path) -> None:
        """A shared dependency is compiled exactly once even with many dependents."""
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "shared.farchml", "interface Common { v: Int }")
        for i in range(4):
            _write(
                src / f"user{i}.farchml",
                f"from app/shared import Common\ncomponent User{i} {{ requires Common }}",
            )
        sources = [src / f"user{i}.farchml" for i in range(4)] + [src / "shared.farchml"]

        result = compile_files(sources, build, {("", "app"): src})
        assert "app/shared" in result
        for i in range(4):
            assert f"app/user{i}" in result

    def test_three_level_dependency_chain(self, tmp_path: Path) -> None:
        """A → B → C dependency chain compiles correctly in the right order."""
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "c.farchml", "interface Base { id: Int }")
        _write(src / "b.farchml", "from app/c import Base\ninterface Mid { b: Int }")
        _write(
            src / "a.farchml",
            "from app/b import Mid\nfrom app/c import Base\ncomponent Top { requires Mid }",
        )

        result = compile_files([src / "a.farchml"], build, {("", "app"): src})
        assert "app/a" in result
        assert "app/b" in result
        assert "app/c" in result

    def test_parallel_compilation_with_diamond_dependency(self, tmp_path: Path) -> None:
        """Diamond: A and B both depend on C, D depends on both A and B."""
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "c.farchml", "interface Base { id: Int }")
        _write(src / "a.farchml", "from app/c import Base\ninterface A { x: Int }")
        _write(src / "b.farchml", "from app/c import Base\ninterface B { y: Int }")
        _write(
            src / "d.farchml",
            "from app/a import A\nfrom app/b import B\ncomponent D { requires A }",
        )

        result = compile_files([src / "d.farchml"], build, {("", "app"): src})
        assert {"app/c", "app/a", "app/b", "app/d"} == set(result.keys())

    def test_duplicate_file_in_input_list_compiled_once(self, tmp_path: Path) -> None:
        """The same file listed multiple times is compiled only once."""
        src = tmp_path / "src"
        build = tmp_path / "build"
        f = src / "x.farchml"
        _write(f, "component X {}")
        result = compile_files([f, f, f], build, {("", "app"): src})
        assert list(result.keys()) == ["app/x"]

    def test_parallel_cache_hit_does_not_rewrite_artifacts(self, tmp_path: Path) -> None:
        """All-cache-hit scenario: no artifacts are rewritten."""
        src = tmp_path / "src"
        build = tmp_path / "build"
        n = 5
        sources = [src / f"f{i}.farchml" for i in range(n)]
        for i, f in enumerate(sources):
            _write(f, f"component F{i} {{}}")

        compile_files(sources, build, {("", "app"): src})
        mtimes_after_first = [_artifact(build, f"app/f{i}").stat().st_mtime for i in range(n)]

        compile_files(sources, build, {("", "app"): src})
        mtimes_after_second = [_artifact(build, f"app/f{i}").stat().st_mtime for i in range(n)]

        assert mtimes_after_first == mtimes_after_second
