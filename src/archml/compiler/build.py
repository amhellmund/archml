# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""ArchML compiler build workflow.

Compiles .archml source files to cached JSON artifacts, performing incremental
dependency resolution and semantic validation.  The workflow mirrors CMake-style
incremental builds: a cached artifact is reused when it is newer than its source.
"""

from __future__ import annotations

from pathlib import Path

from archml.compiler.artifact import read_artifact, write_artifact
from archml.compiler.parser import ParseError, parse
from archml.compiler.semantic_analysis import analyze
from archml.model.entities import ArchFile

# ###############
# Public Interface
# ###############


class CompilerError(Exception):
    """Raised when the compiler cannot successfully build one or more source files.

    This covers missing dependency files, parse errors, and semantic errors.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def compile_files(
    files: list[Path],
    build_dir: Path,
    source_root: Path,
) -> dict[Path, ArchFile]:
    """Compile a list of .archml source files to cached artifacts.

    For each source file the following steps are performed:

    1. If a compiled artifact already exists in *build_dir* **and** is newer
       than the source file, the cached artifact is loaded and returned without
       re-parsing.
    2. Otherwise the source file is parsed.
    3. Each import declared in the file is resolved to a file under
       *source_root* and compiled recursively.  A missing dependency raises
       :class:`CompilerError`.
    4. Semantic analysis is run with the resolved imports.  Any semantic errors
       raise :class:`CompilerError`.
    5. The compiled :class:`~archml.model.entities.ArchFile` is written to
       *build_dir* as a JSON artifact and returned.

    Args:
        files: Input ``.archml`` source files to compile.
        build_dir: Directory where compiled artifacts (``.json``) are stored.
        source_root: Workspace root used to resolve import paths.  An import
            declaration ``from imports/types import …`` resolves to the file
            ``{source_root}/imports/types.archml``.

    Returns:
        Mapping from resolved source-file paths to their compiled
        :class:`~archml.model.entities.ArchFile` models.

    Raises:
        CompilerError: If a dependency file is not found, a source file cannot
            be parsed, or semantic errors are detected.
    """
    source_root = source_root.resolve()
    build_dir = build_dir.resolve()
    compiled: dict[Path, ArchFile] = {}

    for file_path in files:
        _compile_one(file_path.resolve(), build_dir, source_root, compiled, set())

    return compiled


# ################
# Implementation
# ################


def _artifact_path(source_file: Path, source_root: Path, build_dir: Path) -> Path:
    """Return the artifact path for *source_file* inside *build_dir*.

    Preserves the directory structure relative to *source_root* and replaces
    the ``.archml`` extension with ``.json``.  If *source_file* is not under
    *source_root*, the filename alone (without directory) is used.
    """
    try:
        rel = source_file.relative_to(source_root)
    except ValueError:
        rel = Path(source_file.name)
    return build_dir / rel.with_suffix(".json")


def _cache_is_valid(artifact: Path, source_file: Path) -> bool:
    """Return ``True`` when *artifact* exists and is strictly newer than *source_file*."""
    return artifact.exists() and artifact.stat().st_mtime > source_file.stat().st_mtime


def _compile_one(
    source_file: Path,
    build_dir: Path,
    source_root: Path,
    compiled: dict[Path, ArchFile],
    in_progress: set[Path],
) -> ArchFile:
    """Compile a single source file, resolving its dependencies recursively.

    Args:
        source_file: Absolute path to the ``.archml`` file to compile.
        build_dir: Artifact storage directory.
        source_root: Workspace root for import resolution.
        compiled: Accumulator — already-compiled files; updated in place.
        in_progress: Files currently on the call stack; used to detect cycles.

    Returns:
        The compiled :class:`~archml.model.entities.ArchFile`.

    Raises:
        CompilerError: On missing dependencies, parse errors, or semantic errors.
    """
    if source_file in compiled:
        return compiled[source_file]

    if source_file in in_progress:
        raise CompilerError(f"Circular dependency detected involving '{source_file}'")

    artifact = _artifact_path(source_file, source_root, build_dir)
    if _cache_is_valid(artifact, source_file):
        arch_file = read_artifact(artifact)
        compiled[source_file] = arch_file
        return arch_file

    source_text = source_file.read_text(encoding="utf-8")
    try:
        arch_file = parse(source_text)
    except ParseError as exc:
        raise CompilerError(f"Parse error in '{source_file}': {exc}") from exc

    in_progress.add(source_file)
    resolved_imports: dict[str, ArchFile] = {}

    for imp in arch_file.imports:
        dep_file = (source_root / (imp.source_path + ".archml")).resolve()
        if not dep_file.exists():
            in_progress.discard(source_file)
            raise CompilerError(
                f"Dependency '{imp.source_path}' not found "
                f"(expected: '{dep_file}') "
                f"required by '{source_file}'"
            )
        dep_arch = _compile_one(dep_file, build_dir, source_root, compiled, in_progress)
        resolved_imports[imp.source_path] = dep_arch

    in_progress.discard(source_file)

    errors = analyze(arch_file, resolved_imports=resolved_imports if resolved_imports else None)
    if errors:
        msgs = "\n".join(f"  - {e.message}" for e in errors)
        raise CompilerError(f"Semantic errors in '{source_file}':\n{msgs}")

    write_artifact(arch_file, artifact)
    compiled[source_file] = arch_file
    return arch_file
