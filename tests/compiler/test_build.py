# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ArchML compiler build workflow (build.py)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from archml.compiler.artifact import write_artifact
from archml.compiler.build import CompilerError, compile_files
from archml.model.entities import ArchFile

# ###############
# Test data paths
# ###############

DATA_DIR = Path(__file__).parent.parent / "data"
POSITIVE_DIR = DATA_DIR / "positive"
# source_root for compiler/* test files — import paths are relative to this dir
COMPILER_DIR = POSITIVE_DIR / "compiler"
IMPORTS_DIR = POSITIVE_DIR / "imports"


# ###############
# Tests: Single-file compilation (no dependencies)
# ###############


class TestSingleFileCompilation:
    def test_compile_single_file(self, tmp_path: Path) -> None:
        source_file = COMPILER_DIR / "simple.archml"
        result = compile_files([source_file], tmp_path, COMPILER_DIR)

        assert source_file.resolve() in result
        arch = result[source_file.resolve()]
        assert any(c.name == "DataProcessor" for c in arch.components)
        assert any(i.name == "DataRequest" for i in arch.interfaces)
        assert any(i.name == "DataResponse" for i in arch.interfaces)

    def test_artifact_written_to_build_dir(self, tmp_path: Path) -> None:
        source_file = COMPILER_DIR / "simple.archml"
        compile_files([source_file], tmp_path, COMPILER_DIR)

        # Artifact mirrors source path relative to source_root
        artifact = tmp_path / "simple.json"
        assert artifact.exists()

    def test_artifact_content_is_valid_json(self, tmp_path: Path) -> None:
        import json

        source_file = COMPILER_DIR / "simple.archml"
        compile_files([source_file], tmp_path, COMPILER_DIR)

        artifact = tmp_path / "simple.json"
        obj = json.loads(artifact.read_text(encoding="utf-8"))
        assert "v" in obj
        assert "components" in obj


# ###############
# Tests: Multi-file compilation with dependencies
# ###############


class TestMultiFileCompilation:
    def test_compile_file_with_one_dependency(self, tmp_path: Path) -> None:
        source_file = COMPILER_DIR / "worker.archml"
        result = compile_files([source_file], tmp_path, COMPILER_DIR)

        # Both the worker and its dependency (shared/types) should be compiled.
        assert source_file.resolve() in result
        assert (COMPILER_DIR / "shared" / "types.archml").resolve() in result

    def test_dependency_artifact_stored_preserving_structure(self, tmp_path: Path) -> None:
        source_file = COMPILER_DIR / "worker.archml"
        compile_files([source_file], tmp_path, COMPILER_DIR)

        # Artifacts mirror the source directory structure relative to source_root.
        assert (tmp_path / "worker.json").exists()
        assert (tmp_path / "shared" / "types.json").exists()

    def test_compile_deep_dependency_chain(self, tmp_path: Path) -> None:
        """system.archml → worker.archml → shared/types.archml (three levels)."""
        source_file = COMPILER_DIR / "system.archml"
        result = compile_files([source_file], tmp_path, COMPILER_DIR)

        assert source_file.resolve() in result
        assert (COMPILER_DIR / "worker.archml").resolve() in result
        assert (COMPILER_DIR / "shared" / "types.archml").resolve() in result

    def test_compile_multiple_input_files(self, tmp_path: Path) -> None:
        files = [
            COMPILER_DIR / "simple.archml",
            COMPILER_DIR / "worker.archml",
        ]
        result = compile_files(files, tmp_path, COMPILER_DIR)

        assert (COMPILER_DIR / "simple.archml").resolve() in result
        assert (COMPILER_DIR / "worker.archml").resolve() in result

    def test_shared_dependency_compiled_once(self, tmp_path: Path) -> None:
        """When two input files share a dependency it appears once in the result."""
        # Both worker.archml and system.archml depend on shared/types.archml.
        files = [
            COMPILER_DIR / "worker.archml",
            COMPILER_DIR / "system.archml",
        ]
        result = compile_files(files, tmp_path, COMPILER_DIR)

        dep = (COMPILER_DIR / "shared" / "types.archml").resolve()
        assert dep in result

    def test_compile_existing_imports_test_files(self, tmp_path: Path) -> None:
        """Compile the existing multi-file import test data end-to-end."""
        source_file = IMPORTS_DIR / "ecommerce_system.archml"
        result = compile_files([source_file], tmp_path, POSITIVE_DIR)

        assert source_file.resolve() in result
        arch = result[source_file.resolve()]
        assert any(s.name == "ECommerce" for s in arch.systems)


# ###############
# Tests: Caching behaviour
# ###############


class TestCacheBehaviour:
    def test_cache_miss_on_first_compile(self, tmp_path: Path) -> None:
        source_file = COMPILER_DIR / "simple.archml"
        artifact = tmp_path / "simple.json"

        assert not artifact.exists()
        compile_files([source_file], tmp_path, COMPILER_DIR)
        assert artifact.exists()

    def test_cache_hit_skips_reparsing(self, tmp_path: Path) -> None:
        """A pre-existing artifact that is newer than its source is not rewritten."""
        source_file = COMPILER_DIR / "simple.archml"

        compile_files([source_file], tmp_path, COMPILER_DIR)
        artifact = tmp_path / "simple.json"
        first_mtime = artifact.stat().st_mtime

        compile_files([source_file], tmp_path, COMPILER_DIR)
        second_mtime = artifact.stat().st_mtime

        assert first_mtime == second_mtime  # artifact not rewritten on cache hit

    def test_stale_cache_is_recompiled(self, tmp_path: Path) -> None:
        """An artifact that is older than the source is regenerated."""
        source_root = tmp_path / "src"
        source_root.mkdir()
        build_dir = tmp_path / "build"
        source_file = source_root / "minimal.archml"
        source_file.write_text(
            "component A {}\ninterface Ping { field v: Int }",
            encoding="utf-8",
        )

        compile_files([source_file], build_dir, source_root)
        artifact = build_dir / "minimal.json"
        assert artifact.exists()

        # Overwrite the artifact with an empty (stale) model.
        write_artifact(ArchFile(), artifact)

        # Set the artifact mtime to be older than the source so the cache is invalid.
        stale_mtime = source_file.stat().st_mtime - 1
        os.utime(artifact, (stale_mtime, stale_mtime))

        result = compile_files([source_file], build_dir, source_root)
        arch = result[source_file.resolve()]
        # The recompiled artifact should contain the real component, not the stale empty one.
        assert any(c.name == "A" for c in arch.components)

    def test_prebuilt_dependency_artifact_is_used(self, tmp_path: Path) -> None:
        """A dependency whose artifact is newer than its source uses the cached artifact."""
        source_root = tmp_path / "src"
        source_root.mkdir()
        build_dir = tmp_path / "build"

        lib_file = source_root / "lib.archml"
        lib_file.write_text("interface Ping { field v: Int }", encoding="utf-8")

        # Compile the library to produce its artifact.
        compile_files([lib_file], build_dir, source_root)

        # Make lib.archml appear older so its artifact is definitely fresher.
        old_mtime = (build_dir / "lib.json").stat().st_mtime - 10
        os.utime(lib_file, (old_mtime, old_mtime))

        consumer_file = source_root / "consumer.archml"
        consumer_file.write_text(
            "from lib import Ping\ncomponent C { requires Ping }",
            encoding="utf-8",
        )
        result = compile_files([consumer_file], build_dir, source_root)
        arch = result[consumer_file.resolve()]
        assert any(c.name == "C" for c in arch.components)


# ###############
# Tests: Error cases
# ###############


class TestErrorCases:
    def test_missing_dependency_raises_compiler_error(self, tmp_path: Path) -> None:
        source_root = tmp_path / "src"
        source_root.mkdir()
        source_file = source_root / "consumer.archml"
        source_file.write_text(
            "from nonexistent/module import Something\ncomponent C { requires Something }",
            encoding="utf-8",
        )
        with pytest.raises(CompilerError) as exc_info:
            compile_files([source_file], tmp_path / "build", source_root)
        assert "nonexistent/module" in str(exc_info.value)

    def test_semantic_error_raises_compiler_error(self, tmp_path: Path) -> None:
        source_root = tmp_path / "src"
        source_root.mkdir()
        source_file = source_root / "bad.archml"
        source_file.write_text(
            "component C { requires UndefinedInterface }",
            encoding="utf-8",
        )
        with pytest.raises(CompilerError) as exc_info:
            compile_files([source_file], tmp_path / "build", source_root)
        assert "Semantic errors" in str(exc_info.value)
        assert "UndefinedInterface" in str(exc_info.value)

    def test_parse_error_raises_compiler_error(self, tmp_path: Path) -> None:
        source_root = tmp_path / "src"
        source_root.mkdir()
        source_file = source_root / "broken.archml"
        source_file.write_text("component { }", encoding="utf-8")  # missing name
        with pytest.raises(CompilerError) as exc_info:
            compile_files([source_file], tmp_path / "build", source_root)
        assert "Parse error" in str(exc_info.value)

    def test_circular_dependency_raises_compiler_error(self, tmp_path: Path) -> None:
        source_root = tmp_path / "src"
        source_root.mkdir()
        a_file = source_root / "a.archml"
        b_file = source_root / "b.archml"
        # a imports b; b imports a → cycle
        a_file.write_text("from b import BIface\ninterface AIface { field x: Int }", encoding="utf-8")
        b_file.write_text("from a import AIface\ninterface BIface { field y: Int }", encoding="utf-8")

        with pytest.raises(CompilerError) as exc_info:
            compile_files([a_file], tmp_path / "build", source_root)
        assert "Circular dependency" in str(exc_info.value)

    def test_error_message_includes_source_file_name(self, tmp_path: Path) -> None:
        source_root = tmp_path / "src"
        source_root.mkdir()
        source_file = source_root / "my_service.archml"
        source_file.write_text(
            "component C { requires Nope }",
            encoding="utf-8",
        )
        with pytest.raises(CompilerError) as exc_info:
            compile_files([source_file], tmp_path / "build", source_root)
        assert "my_service.archml" in str(exc_info.value)

    def test_dependency_semantic_error_is_reported(self, tmp_path: Path) -> None:
        """Semantic errors in a dependency are surfaced, not silently ignored."""
        source_root = tmp_path / "src"
        source_root.mkdir()
        bad_lib = source_root / "badlib.archml"
        # duplicate enum name → semantic error in the dependency
        bad_lib.write_text("enum Status { A }\nenum Status { B }", encoding="utf-8")
        consumer = source_root / "consumer.archml"
        consumer.write_text(
            "from badlib import Status\ncomponent C { }",
            encoding="utf-8",
        )
        with pytest.raises(CompilerError):
            compile_files([consumer], tmp_path / "build", source_root)


# ###############
# Tests: Return value and edge cases
# ###############


class TestReturnValueAndEdgeCases:
    def test_return_value_contains_compiled_model(self, tmp_path: Path) -> None:
        source_file = COMPILER_DIR / "shared" / "types.archml"
        result = compile_files([source_file], tmp_path, COMPILER_DIR)
        arch = result[source_file.resolve()]

        assert any(e.name == "Priority" for e in arch.enums)
        assert any(t.name == "TaskItem" for t in arch.types)
        assert any(i.name == "TaskRequest" for i in arch.interfaces)

    def test_empty_file_list_returns_empty_dict(self, tmp_path: Path) -> None:
        result = compile_files([], tmp_path, tmp_path)
        assert result == {}

    def test_result_keys_are_resolved_absolute_paths(self, tmp_path: Path) -> None:
        source_file = COMPILER_DIR / "simple.archml"
        result = compile_files([source_file], tmp_path, COMPILER_DIR)

        for key in result:
            assert key.is_absolute()

    def test_compile_file_outside_source_root(self, tmp_path: Path) -> None:
        """A file not under source_root uses its filename alone for the artifact."""
        source_root = tmp_path / "src"
        source_root.mkdir()
        build_dir = tmp_path / "build"
        # Place source file outside source_root.
        outside_file = tmp_path / "standalone.archml"
        outside_file.write_text("interface Signal { field v: Int }", encoding="utf-8")

        compile_files([outside_file], build_dir, source_root)
        assert (build_dir / "standalone.json").exists()

    def test_compile_all_positive_imports_test_files(self, tmp_path: Path) -> None:
        """All three layered import test files compile together cleanly."""
        files = [
            IMPORTS_DIR / "types.archml",
            IMPORTS_DIR / "order_service.archml",
            IMPORTS_DIR / "ecommerce_system.archml",
        ]
        result = compile_files(files, tmp_path, POSITIVE_DIR)
        assert len(result) == 3
