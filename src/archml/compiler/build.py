# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Incremental compiler workflow for .archml files.

Implements a CMake-style cache: an artifact is reused when it already exists
and is strictly newer than the corresponding source file.  Dependencies are
compiled recursively before the dependent file is validated.
"""

from __future__ import annotations

from pathlib import Path

from archml.compiler.artifact import ARTIFACT_SUFFIX, read_artifact, write_artifact
from archml.compiler.parser import ParseError, parse
from archml.compiler.semantic_analysis import analyze
from archml.model.entities import ArchFile

# ###############
# Public Interface
# ###############


class CompilerError(Exception):
    """Raised when the compiler encounters any unrecoverable error.

    Covers parse errors, missing dependencies, semantic errors, and
    circular dependency cycles.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


def compile_files(
    files: list[Path],
    build_dir: Path,
    source_root: Path,
) -> dict[str, ArchFile]:
    """Compile a list of .archml source files.

    For each file, the compiler:
    1. Checks whether an up-to-date artifact already exists (cache hit).
    2. Parses the source file if no valid cache is found.
    3. Recursively compiles all declared imports before the current file.
    4. Runs semantic validation with the resolved import map.
    5. Writes the artifact to *build_dir* (mirroring the source layout).

    Args:
        files: Absolute paths to the .archml source files to compile.
        build_dir: Root directory for compiled artifacts.
        source_root: Root directory that all source files are relative to;
            used to compute artifact paths and import resolution.

    Returns:
        A mapping from source-relative path strings (e.g. ``"shared/types"``)
        to their compiled :class:`~archml.model.entities.ArchFile` models.

    Raises:
        CompilerError: On parse errors, missing imports, semantic errors, or
            circular dependencies.
    """
    compiled: dict[str, ArchFile] = {}
    in_progress: set[str] = set()
    for f in files:
        _compile_file(f, build_dir, source_root, compiled, in_progress)
    return compiled


# ################
# Implementation
# ################


def _artifact_path(source_file: Path, build_dir: Path, source_root: Path) -> Path:
    """Return the artifact path that mirrors *source_file* under *build_dir*."""
    rel = source_file.relative_to(source_root)
    artifact_name = rel.stem + ARTIFACT_SUFFIX
    return build_dir / rel.parent / artifact_name


def _is_up_to_date(source_file: Path, artifact: Path) -> bool:
    """Return True if *artifact* exists and is strictly newer than *source_file*."""
    if not artifact.exists():
        return False
    return artifact.stat().st_mtime > source_file.stat().st_mtime


def _rel_key(source_file: Path, source_root: Path) -> str:
    """Return the canonical key for a source file (path without extension)."""
    rel = source_file.relative_to(source_root)
    return str(rel.with_suffix(""))


def _compile_file(
    source_file: Path,
    build_dir: Path,
    source_root: Path,
    compiled: dict[str, ArchFile],
    in_progress: set[str],
) -> ArchFile:
    """Compile one .archml file, recursively compiling its dependencies first.

    Args:
        source_file: Absolute path to the .archml file to compile.
        build_dir: Root directory for compiled artifacts.
        source_root: Root directory that all source files are relative to.
        compiled: Accumulator mapping already-compiled relative keys to models.
        in_progress: Set of relative keys currently being compiled (cycle guard).

    Returns:
        The compiled :class:`~archml.model.entities.ArchFile` for *source_file*.

    Raises:
        CompilerError: On any compilation failure.
    """
    key = _rel_key(source_file, source_root)

    if key in compiled:
        return compiled[key]

    if key in in_progress:
        raise CompilerError(f"Circular dependency detected involving '{key}'")

    artifact = _artifact_path(source_file, build_dir, source_root)

    if _is_up_to_date(source_file, artifact):
        arch_file = read_artifact(artifact)
        compiled[key] = arch_file
        return arch_file

    # Parse the source file.
    try:
        source_text = source_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise CompilerError(f"Cannot read source file '{source_file}': {exc}") from exc

    try:
        arch_file = parse(source_text)
    except ParseError as exc:
        raise CompilerError(f"Parse error in '{source_file}': {exc}") from exc

    in_progress.add(key)
    try:
        # Recursively compile all imported dependencies.
        resolved_imports: dict[str, ArchFile] = {}
        for imp in arch_file.imports:
            dep_source = source_root / (imp.source_path + ".archml")
            if not dep_source.exists():
                raise CompilerError(
                    f"Dependency '{imp.source_path}' of '{source_file}' not found (expected '{dep_source}')"
                )
            dep = _compile_file(dep_source, build_dir, source_root, compiled, in_progress)
            resolved_imports[imp.source_path] = dep

        # Semantic validation.
        errors = analyze(arch_file, resolved_imports=resolved_imports)
        if errors:
            error_lines = "\n".join(f"  {e.message}" for e in errors)
            raise CompilerError(f"Semantic errors in '{source_file}':\n{error_lines}")

        # Write artifact.
        artifact.parent.mkdir(parents=True, exist_ok=True)
        write_artifact(arch_file, artifact)

    finally:
        in_progress.discard(key)

    compiled[key] = arch_file
    return arch_file
