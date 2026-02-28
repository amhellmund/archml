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


def _artifact(build_dir: Path, source_root: Path, source: Path) -> Path:
    """Return the expected artifact path for a source file."""
    rel = source.relative_to(source_root)
    return build_dir / rel.parent / (rel.stem + ARTIFACT_SUFFIX)


# ###############
# Single-file compilation
# ###############


class TestSingleFile:
    def test_compiles_simple_file(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(
            src / "simple.archml",
            """
interface Signal { field v: Int }
component A { provides Signal }
""",
        )
        result = compile_files([src / "simple.archml"], build, src)
        assert "simple" in result
        assert result["simple"].components[0].name == "A"

    def test_artifact_written_to_build_dir(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        source = src / "x.archml"
        _write(source, "component C {}")
        compile_files([source], build, src)
        artifact = _artifact(build, src, source)
        assert artifact.exists()

    def test_artifact_can_be_read_back(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        source = src / "x.archml"
        _write(source, "component MyComp {}")
        compile_files([source], build, src)
        artifact = _artifact(build, src, source)
        af = read_artifact(artifact)
        assert af.components[0].name == "MyComp"

    def test_compiles_file_with_enum_and_type(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(
            src / "types.archml",
            """
enum Color { Red Green Blue }
type Point { field x: Int field y: Int }
""",
        )
        result = compile_files([src / "types.archml"], build, src)
        af = result["types"]
        assert af.enums[0].name == "Color"
        assert af.types[0].name == "Point"


# ###############
# Cache behaviour
# ###############


class TestCache:
    def test_cache_hit_skips_recompile(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        source = src / "x.archml"
        _write(source, "component A {}")  # mtime set 2s in the past

        compile_files([source], build, src)
        artifact = _artifact(build, src, source)
        mtime_first = artifact.stat().st_mtime

        compile_files([source], build, src)
        mtime_second = artifact.stat().st_mtime

        assert mtime_first == mtime_second  # artifact was NOT rewritten

    def test_stale_artifact_triggers_recompile(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        source = src / "x.archml"
        _write(source, "component A {}")  # mtime 2s in the past

        compile_files([source], build, src)
        artifact = _artifact(build, src, source)
        content_first = artifact.read_text(encoding="utf-8")

        # Touch the source file to make it newer than the artifact.
        _write(source, "component B {}", mtime_offset=2.0)  # mtime = 2s in the future

        compile_files([source], build, src)
        content_second = artifact.read_text(encoding="utf-8")

        assert content_second != content_first  # artifact was rewritten with new content

    def test_stale_artifact_reads_updated_content(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        source = src / "x.archml"
        _write(source, "component A {}", mtime_offset=-2.0)

        compile_files([source], build, src)

        _write(source, "component NewComp {}", mtime_offset=2.0)  # 2s in future = newer than artifact
        result = compile_files([source], build, src)

        assert result["x"].components[0].name == "NewComp"


# ###############
# Multi-file compilation
# ###############


class TestMultiFile:
    def test_compiles_file_with_dependency(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(
            src / "types.archml",
            "interface Signal { field v: Int }",
        )
        _write(
            src / "app.archml",
            """
from types import Signal
component Worker { requires Signal }
""",
        )
        result = compile_files([src / "app.archml"], build, src)
        assert "app" in result
        assert "types" in result

    def test_dependency_artifact_also_written(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "types.archml", "interface Signal { field v: Int }")
        _write(src / "app.archml", "from types import Signal\ncomponent W { requires Signal }")
        compile_files([src / "app.archml"], build, src)
        types_artifact = _artifact(build, src, src / "types.archml")
        assert types_artifact.exists()

    def test_three_level_dependency_chain(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "base.archml", "interface IBase { field x: Int }")
        _write(src / "mid.archml", "from base import IBase\ncomponent Mid { requires IBase }")
        _write(src / "top.archml", "from base import IBase\nfrom mid import Mid\ncomponent Top { requires IBase }")
        result = compile_files([src / "top.archml"], build, src)
        assert "base" in result
        assert "mid" in result
        assert "top" in result

    def test_shared_dependency_compiled_once(self, tmp_path: Path) -> None:
        """Two top-level files sharing a dependency don't recompile it."""
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "shared.archml", "interface I { field v: Int }")
        _write(src / "a.archml", "from shared import I\ncomponent A { requires I }")
        _write(src / "b.archml", "from shared import I\ncomponent B { requires I }")
        result = compile_files([src / "a.archml", src / "b.archml"], build, src)
        assert "shared" in result
        assert "a" in result
        assert "b" in result

    def test_subdirectory_dependency(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "shared" / "types.archml", "interface Signal { field v: Int }")
        _write(
            src / "worker.archml",
            "from shared/types import Signal\ncomponent Worker { requires Signal }",
        )
        result = compile_files([src / "worker.archml"], build, src)
        assert "worker" in result
        assert "shared/types" in result

    def test_compiled_from_test_data(self, tmp_path: Path) -> None:
        """Compile the realistic multi-file test data under tests/data/positive/compiler/."""
        result = compile_files(
            [DATA_DIR / "system.archml"],
            tmp_path / "build",
            DATA_DIR.parent,
        )
        assert "compiler/system" in result
        assert "compiler/worker" in result
        assert "compiler/shared/types" in result


# ###############
# Error cases
# ###############


class TestErrorCases:
    def test_parse_error_raises_compiler_error(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "bad.archml", "component {}")  # missing name
        with pytest.raises(CompilerError, match="Parse error"):
            compile_files([src / "bad.archml"], build, src)

    def test_missing_dependency_raises_compiler_error(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "app.archml", "from nonexistent import Something\ncomponent C {}")
        with pytest.raises(CompilerError, match="not found"):
            compile_files([src / "app.archml"], build, src)

    def test_semantic_error_raises_compiler_error(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(
            src / "bad.archml",
            "component C { requires UnknownInterface }",
        )
        with pytest.raises(CompilerError, match="Semantic errors"):
            compile_files([src / "bad.archml"], build, src)

    def test_circular_dependency_raises_compiler_error(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        # a imports b, b imports a
        _write(src / "a.archml", "from b import Something\ncomponent A {}")
        _write(src / "b.archml", "from a import Something\ncomponent B {}")
        with pytest.raises(CompilerError, match="Circular dependency"):
            compile_files([src / "a.archml"], build, src)

    def test_compiler_error_message_includes_file_path(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "myfile.archml", "component {}")
        with pytest.raises(CompilerError) as exc_info:
            compile_files([src / "myfile.archml"], build, src)
        assert "myfile" in str(exc_info.value)

    def test_multiple_semantic_errors_in_message(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(
            src / "bad.archml",
            """
enum Dup { A }
enum Dup { B }
""",
        )
        with pytest.raises(CompilerError, match="Semantic errors"):
            compile_files([src / "bad.archml"], build, src)


# ###############
# Return value
# ###############


class TestReturnValue:
    def test_returns_empty_dict_for_no_files(self, tmp_path: Path) -> None:
        result = compile_files([], tmp_path / "build", tmp_path / "src")
        assert result == {}

    def test_key_uses_relative_path_without_extension(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "subdir" / "myfile.archml", "component C {}")
        result = compile_files([src / "subdir" / "myfile.archml"], build, src)
        assert "subdir/myfile" in result

    def test_compiling_same_file_twice_returns_same_model(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        build = tmp_path / "build"
        _write(src / "x.archml", "component C {}")
        result = compile_files([src / "x.archml", src / "x.archml"], build, src)
        assert len(result) == 1
        assert "x" in result
