# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Incremental compiler workflow for .archml files.

Implements a CMake-style cache: an artifact is reused when it already exists
and is strictly newer than the corresponding source file.  All files are
parsed in parallel; semantic validation is then performed in topological
waves so that each wave's files run concurrently once their dependencies
have been compiled.

Two forms of cross-file import are supported:

* **Local workspace imports** — ``from mnemonic/path/to/file import …``
  The first path segment is the mnemonic name.  It is looked up as
  ``(source_repo, mnemonic)`` in the caller-supplied *source_import_map*
  (``{(repo_id, mnemonic): absolute_base_path}``), where *source_repo* is the
  repository identifier of the file performing the import.

* **Remote git imports** — ``from @repo/mnemonic/path/to/file import …``
  The ``@repo`` prefix identifies a named Git repository configured in the
  workspace.  The ``mnemonic`` segment selects a named source tree within
  that repository.  The caller-supplied *source_import_map* must contain an
  entry keyed as ``("@repo", "mnemonic")`` pointing to the locally synced
  directory (populated by ``archml sync-remote``).  If the key is absent,
  :class:`CompilerError` is raised with a message directing the user to run
  ``archml sync-remote``.

Every source file belongs to exactly one repository, identified by the
*repo_id* of the ``(repo_id, mnemonic)`` entry whose base path contains the
file.  Bare mnemonic imports (without ``@repo``) are resolved relative to the
source file's repository.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from archml.compiler.artifact import ARTIFACT_SUFFIX, read_artifact, write_artifact
from archml.compiler.parser import ParseError, parse
from archml.compiler.scanner import LexerError
from archml.compiler.semantic_analysis import analyze
from archml.model.entities import ArchFile

# ###############
# Public Interface
# ###############


class SourceImportKey(NamedTuple):
    """Typed key for the source-import map.

    *repo* identifies the repository: a plain workspace name (e.g. ``"myapp"``)
    for local imports, or an ``@``-prefixed remote name (e.g. ``"@payments"``)
    for git imports.  It must never be empty.

    *mnemonic* is the named source tree within that repository.
    """

    repo: str
    mnemonic: str


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
    source_import_map: dict[SourceImportKey, Path],
) -> dict[str, ArchFile]:
    """Compile a list of .archml source files in parallel.

    For each file, the compiler:
    1. Checks whether an up-to-date artifact already exists (cache hit).
    2. On a cache hit, validates that all declared imports still exist so that
       a file moved to a different path triggers a recompile of its dependents.
    3. Parses all files and their transitive dependencies in parallel.
    4. Compiles files in topological waves: each wave consists of all files
       whose dependencies are fully compiled, and all files in a wave are
       compiled concurrently.
    5. Runs semantic validation with the resolved import map.
    6. Writes the artifact to *build_dir* (mirroring the source layout).

    Args:
        files: Absolute paths to the .archml source files to compile.
        build_dir: Root directory for compiled artifacts.
        source_import_map: Mapping from :class:`SourceImportKey` pairs to
            absolute base paths.  Local mnemonics use the workspace name as
            *repo* (e.g. ``SourceImportKey("myapp", "myapp")``); remote
            repositories use their ``"@name"`` identifier
            (e.g. ``SourceImportKey("@payments", "lib")``).
            Import paths of the form ``mnemonic/rel`` are resolved by
            looking up ``(source_repo, mnemonic)`` and appending *rel*.
            Remote imports ``@repo/mnemonic/rel`` use ``("@repo", mnemonic)``.

    Returns:
        A mapping from canonical path keys (e.g. ``"myapp/types"`` or
        ``"@payments/lib/types"``) to their compiled
        :class:`~archml.model.entities.ArchFile` models.

    Raises:
        CompilerError: On parse errors, missing imports, unsupported remote
            imports, semantic errors, or circular dependencies.
    """
    results = _discover_all(files, build_dir, source_import_map)
    return _compile_in_waves(results, build_dir)


# ################
# Implementation
# ################


@dataclass
class _ParseResult:
    """Intermediate state for a single .archml file after the parse phase."""

    key: str
    """Canonical key, e.g. ``"myapp/types"`` or ``"@payments/lib/types"``."""

    source_path: Path
    """Absolute path to the source file."""

    arch_file: ArchFile
    """Parsed (or cache-loaded) model."""

    dep_items: list[tuple[str, Path]] = field(default_factory=list)
    """``(dep_key, dep_source_path)`` pairs for each declared import."""

    is_cached: bool = False
    """True when *arch_file* was loaded from an existing up-to-date artifact."""


def _get_source_repo(source_file: Path, source_import_map: dict[SourceImportKey, Path]) -> str:
    """Return the repository identifier for *source_file*.

    Iterates over all ``(repo_id, mnemonic)`` entries and returns the
    *repo_id* of the entry whose base path contains *source_file*.

    Raises:
        CompilerError: If the file is not under any configured mnemonic base path.
    """
    for (repo_id, _mnemonic), base_path in source_import_map.items():
        try:
            source_file.relative_to(base_path)
            return repo_id
        except ValueError:
            continue
    raise CompilerError(f"Source file '{source_file}' is not under any configured mnemonic base path")


def _rel_key(source_file: Path, source_import_map: dict[SourceImportKey, Path]) -> str:
    """Return the canonical key for a source file (path without extension).

    For local files (repo not starting with ``"@"``), the key is
    ``"mnemonic/rel"`` (e.g. ``"myapp/shared/types"``).

    For remote files (repo starting with ``"@"``), the key is
    ``"@repo/mnemonic/rel"`` (e.g. ``"@payments/lib/types"``).

    Raises:
        CompilerError: If the file is not under any configured base path.
    """
    for (repo_id, mnemonic), base_path in source_import_map.items():
        try:
            rel = source_file.relative_to(base_path)
            rel_str = str(rel.with_suffix("")).replace("\\", "/")
            if not repo_id.startswith("@"):
                return f"{mnemonic}/{rel_str}"
            else:
                return f"{repo_id}/{mnemonic}/{rel_str}"
        except ValueError:
            continue

    raise CompilerError(f"Source file '{source_file}' is not under any configured mnemonic base path")


def _artifact_path(key: str, build_dir: Path) -> Path:
    """Return the artifact path for a given canonical key.

    The key segments (split on ``/``) map directly to subdirectory components
    under *build_dir* (e.g. ``"myapp/types"`` → ``build_dir/myapp/types.archml.json``).
    """
    parts = key.split("/")
    artifact_dir = build_dir
    for part in parts[:-1]:
        artifact_dir = artifact_dir / part
    return artifact_dir / (parts[-1] + ARTIFACT_SUFFIX)


def _is_up_to_date(source_file: Path, artifact: Path) -> bool:
    """Return True if *artifact* exists and is strictly newer than *source_file*."""
    if not artifact.exists():
        return False
    return artifact.stat().st_mtime > source_file.stat().st_mtime


def _resolve_import_source(
    import_path: str,
    source_import_map: dict[SourceImportKey, Path],
    source_repo: str,
) -> Path:
    """Resolve an import path to the absolute path of the ``.archml`` source file.

    Args:
        import_path: The raw import path string as stored in :class:`ImportDeclaration`.
            Must be one of:
            - ``"mnemonic/path/to/file"`` — resolved using *source_repo*
            - ``"@repo/mnemonic/path/to/file"`` — resolved using the named
              remote repository and mnemonic
        source_import_map: Mapping from :class:`SourceImportKey` to base paths.
        source_repo: Repository identifier of the file performing the import
            (workspace name for local, ``"@repo"`` for remote).

    Returns:
        Absolute path to the ``.archml`` file (which may or may not exist).

    Raises:
        CompilerError: If *import_path* has an invalid format or if the
            required mnemonic is absent from *source_import_map*.
    """
    if import_path.startswith("@"):
        # Format: @repo/mnemonic/path/to/file
        slash1 = import_path.find("/", 1)
        if slash1 == -1:
            raise CompilerError(f"Invalid remote import '{import_path}': expected '@repo/mnemonic/path' format")
        repo_id = import_path[:slash1]  # e.g. "@payments"
        rest = import_path[slash1 + 1 :]  # e.g. "lib/types" or "lib/shared/types"
        slash2 = rest.find("/")
        if slash2 == -1:
            raise CompilerError(
                f"Invalid remote import '{import_path}': expected '@repo/mnemonic/path' format "
                "(missing path component after mnemonic)"
            )
        mnemonic = rest[:slash2]  # e.g. "lib"
        path = rest[slash2 + 1 :]  # e.g. "types" or "shared/types"
        key = SourceImportKey(repo_id, mnemonic)
        if key not in source_import_map:
            raise CompilerError(
                f"Remote import '{import_path}': mnemonic '{mnemonic}' in repository '{repo_id}' "
                "not found in workspace. Run 'archml sync-remote' to download remote repositories."
            )
        return source_import_map[key] / (path + ".archml")

    # Format: mnemonic/path/to/file
    slash1 = import_path.find("/")
    if slash1 == -1:
        raise CompilerError(
            f"Invalid import '{import_path}': expected 'mnemonic/path' format "
            "(imports must start with a mnemonic name followed by a path)"
        )
    mnemonic = import_path[:slash1]  # e.g. "mylib"
    path = import_path[slash1 + 1 :]  # e.g. "types" or "shared/types"
    key = SourceImportKey(source_repo, mnemonic)
    if key not in source_import_map:
        raise CompilerError(f"Import '{import_path}': mnemonic '{mnemonic}' not found in workspace configuration")
    return source_import_map[key] / (path + ".archml")


def _parse_one(
    source_path: Path,
    key: str,
    build_dir: Path,
    source_import_map: dict[SourceImportKey, Path],
) -> _ParseResult:
    """Parse or load one .archml file and compute its direct dependency paths.

    On a cache hit (artifact newer than source and all import sources still
    present), the artifact is loaded directly.  Otherwise the source is parsed
    from disk.

    Raises:
        CompilerError: On any I/O, parse, or import-resolution failure.
    """
    source_repo = _get_source_repo(source_path, source_import_map)
    artifact = _artifact_path(key, build_dir)

    if _is_up_to_date(source_path, artifact):
        arch_file = read_artifact(artifact)
        dep_items: list[tuple[str, Path]] = []
        deps_valid = True
        for imp in arch_file.imports:
            try:
                dep_source = _resolve_import_source(imp.source_path, source_import_map, source_repo)
            except CompilerError:
                deps_valid = False
                break
            if not dep_source.exists():
                deps_valid = False
                break
            dep_items.append((imp.source_path, dep_source))
        if deps_valid:
            return _ParseResult(
                key=key,
                source_path=source_path,
                arch_file=arch_file,
                dep_items=dep_items,
                is_cached=True,
            )

    # Cache miss or stale — parse from source.
    try:
        source_text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CompilerError(f"Cannot read source file '{source_path}': {exc}") from exc

    try:
        arch_file = parse(source_text, filename=source_path.name)
    except (LexerError, ParseError) as exc:
        raise CompilerError(str(exc)) from exc

    dep_items = []
    for imp in arch_file.imports:
        dep_source = _resolve_import_source(imp.source_path, source_import_map, source_repo)
        if not dep_source.exists():
            raise CompilerError(
                f"Dependency '{imp.source_path}' of '{source_path}' not found (expected '{dep_source}')"
            )
        dep_items.append((imp.source_path, dep_source))

    return _ParseResult(
        key=key,
        source_path=source_path,
        arch_file=arch_file,
        dep_items=dep_items,
        is_cached=False,
    )


def _discover_all(
    files: list[Path],
    build_dir: Path,
    source_import_map: dict[SourceImportKey, Path],
) -> dict[str, _ParseResult]:
    """Parse all source files and their transitive dependencies in parallel.

    Uses a BFS-style loop: each iteration submits the current batch to a
    thread pool, then collects newly discovered dependency files for the next
    batch.  Files already enqueued are skipped to avoid duplicate work.

    Returns:
        A mapping from canonical key to :class:`_ParseResult` covering every
        file reachable from the initial *files* list.

    Raises:
        CompilerError: If any file fails to parse or a dependency cannot be
            resolved.  The first error encountered is re-raised.
    """
    results: dict[str, _ParseResult] = {}
    enqueued: set[str] = set()

    to_process: list[tuple[Path, str]] = []
    for f in files:
        k = _rel_key(f, source_import_map)
        if k not in enqueued:
            enqueued.add(k)
            to_process.append((f, k))

    while to_process:
        batch = to_process
        to_process = []
        future_map: dict[Future[_ParseResult], str] = {}
        with ThreadPoolExecutor() as executor:
            for src, k in batch:
                fut = executor.submit(_parse_one, src, k, build_dir, source_import_map)
                future_map[fut] = k
        # All futures are complete after the executor context exits.
        for fut, k in future_map.items():
            result = fut.result()  # re-raises any CompilerError from the thread
            results[k] = result
            for dep_key, dep_path in result.dep_items:
                if dep_key not in enqueued:
                    enqueued.add(dep_key)
                    to_process.append((dep_path, dep_key))

    return results


def _compile_one(
    result: _ParseResult,
    compiled_deps: dict[str, ArchFile],
    build_dir: Path,
) -> ArchFile:
    """Run semantic analysis and write the artifact for one file.

    For cached files the artifact is already up-to-date; the in-memory model
    is returned immediately without re-running analysis.

    Args:
        result: Parse result for the file to compile.
        compiled_deps: All already-compiled files (must contain every direct
            dependency of *result*).
        build_dir: Root directory for compiled artifacts.

    Returns:
        The compiled :class:`~archml.model.entities.ArchFile`.

    Raises:
        CompilerError: On semantic errors.
    """
    if result.is_cached:
        return result.arch_file

    resolved_imports = {dep_key: compiled_deps[dep_key] for dep_key, _ in result.dep_items}

    errors = analyze(
        result.arch_file,
        resolved_imports=resolved_imports,
        file_key=result.key,
        filename=result.source_path.name,
    )
    if errors:
        raise CompilerError("\n".join(str(e) for e in errors))

    artifact = _artifact_path(result.key, build_dir)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    write_artifact(result.arch_file, artifact)

    return result.arch_file


def _compile_in_waves(
    results: dict[str, _ParseResult],
    build_dir: Path,
) -> dict[str, ArchFile]:
    """Compile parsed files in topological waves, each wave running in parallel.

    A wave consists of all files whose direct dependencies are already in the
    *compiled* map.  Files in the same wave are independent of each other and
    are compiled concurrently via a thread pool.

    Raises:
        CompilerError: On semantic errors or if a circular dependency is
            detected (no wave can make progress).
    """
    compiled: dict[str, ArchFile] = {}
    remaining = set(results.keys())

    while remaining:
        wave = {key for key in remaining if all(dep_key in compiled for dep_key, _ in results[key].dep_items)}

        if not wave:
            cycle = ", ".join(sorted(remaining))
            raise CompilerError(f"Circular dependency detected among: {cycle}")

        future_map: dict[Future[ArchFile], str] = {}
        with ThreadPoolExecutor() as executor:
            for key in wave:
                fut = executor.submit(_compile_one, results[key], compiled, build_dir)
                future_map[fut] = key
        # All futures are complete after the executor context exits.
        for fut, key in future_map.items():
            compiled[key] = fut.result()
            remaining.discard(key)

    return compiled
