# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Incremental compiler workflow for .archml files.

Implements a CMake-style cache: an artifact is reused when it already exists
and is strictly newer than the corresponding source file.  Dependencies are
compiled recursively before the dependent file is validated.

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
    source_import_map: dict[tuple[str, str], Path],
) -> dict[str, ArchFile]:
    """Compile a list of .archml source files.

    For each file, the compiler:
    1. Checks whether an up-to-date artifact already exists (cache hit).
    2. On a cache hit, validates that all declared imports still exist so that
       a file moved to a different path triggers a recompile of its dependents.
    3. Parses the source file if no valid cache is found.
    4. Recursively compiles all declared imports before the current file.
    5. Runs semantic validation with the resolved import map.
    6. Writes the artifact to *build_dir* (mirroring the source layout).

    Args:
        files: Absolute paths to the .archml source files to compile.
        build_dir: Root directory for compiled artifacts.
        source_import_map: Mapping from ``(repo_id, mnemonic)`` pairs to
            absolute base paths.  Local mnemonics use ``""`` as *repo_id*
            (e.g. ``("", "myapp")``); remote repositories use their
            ``"@name"`` identifier (e.g. ``("@payments", "lib")``).
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
    compiled: dict[str, ArchFile] = {}
    in_progress: set[str] = set()
    for f in files:
        _compile_file(f, build_dir, source_import_map, compiled, in_progress)
    return compiled


# ################
# Implementation
# ################


def _get_source_repo(source_file: Path, source_import_map: dict[tuple[str, str], Path]) -> str:
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
    raise CompilerError(
        f"Source file '{source_file}' is not under any configured mnemonic base path"
    )


def _rel_key(source_file: Path, source_import_map: dict[tuple[str, str], Path]) -> str:
    """Return the canonical key for a source file (path without extension).

    For local files (repo_id ``""``), the key is ``"mnemonic/rel"``
    (e.g. ``"myapp/shared/types"``).

    For remote files (repo_id ``"@repo"``), the key is
    ``"@repo/mnemonic/rel"`` (e.g. ``"@payments/lib/types"``).

    Raises:
        CompilerError: If the file is not under any configured base path.
    """
    for (repo_id, mnemonic), base_path in source_import_map.items():
        try:
            rel = source_file.relative_to(base_path)
            rel_str = str(rel.with_suffix("")).replace("\\", "/")
            if repo_id == "":
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
    source_import_map: dict[tuple[str, str], Path],
    source_repo: str,
) -> Path:
    """Resolve an import path to the absolute path of the ``.archml`` source file.

    Args:
        import_path: The raw import path string as stored in :class:`ImportDeclaration`.
            Must be one of:
            - ``"mnemonic/path/to/file"`` — resolved using *source_repo*
            - ``"@repo/mnemonic/path/to/file"`` — resolved using the named
              remote repository and mnemonic
        source_import_map: Mapping from ``(repo_id, mnemonic)`` to base paths.
        source_repo: Repository identifier of the file performing the import
            (``""`` for local workspace, ``"@repo"`` for remote).

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
            raise CompilerError(
                f"Invalid remote import '{import_path}': expected '@repo/mnemonic/path' format"
            )
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
        key = (repo_id, mnemonic)
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
    key = (source_repo, mnemonic)
    if key not in source_import_map:
        raise CompilerError(
            f"Import '{import_path}': mnemonic '{mnemonic}' not found in workspace configuration"
        )
    return source_import_map[key] / (path + ".archml")


def _compile_file(
    source_file: Path,
    build_dir: Path,
    source_import_map: dict[tuple[str, str], Path],
    compiled: dict[str, ArchFile],
    in_progress: set[str],
    *,
    _key: str | None = None,
) -> ArchFile:
    """Compile one .archml file, recursively compiling its dependencies first.

    Args:
        source_file: Absolute path to the .archml file to compile.
        build_dir: Root directory for compiled artifacts.
        source_import_map: Mapping from ``(repo_id, mnemonic)`` to base paths.
        compiled: Accumulator mapping already-compiled canonical keys to models.
        in_progress: Set of canonical keys currently being compiled (cycle guard).
        _key: Optional pre-computed canonical key.  When provided (always the
            case for dependency files resolved via ``_resolve_import_source``),
            the key is used directly without inferring it from the filesystem
            path.

    Returns:
        The compiled :class:`~archml.model.entities.ArchFile` for *source_file*.

    Raises:
        CompilerError: On any compilation failure.
    """
    key = _key if _key is not None else _rel_key(source_file, source_import_map)
    source_repo = _get_source_repo(source_file, source_import_map)

    if key in compiled:
        return compiled[key]

    if key in in_progress:
        raise CompilerError(f"Circular dependency detected involving '{key}'")

    artifact = _artifact_path(key, build_dir)

    if _is_up_to_date(source_file, artifact):
        arch_file = read_artifact(artifact)
        # Validate that all declared imports still resolve to existing files.
        # If any dependency has moved (its FQN changed), the cache is stale
        # and we fall through to recompile.
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
        if deps_valid:
            # Recursively ensure all dependencies are also loaded into the
            # result map so callers see the full transitive closure.
            for imp in arch_file.imports:
                dep_source = _resolve_import_source(imp.source_path, source_import_map, source_repo)
                _compile_file(
                    dep_source,
                    build_dir,
                    source_import_map,
                    compiled,
                    in_progress,
                    _key=imp.source_path,
                )
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
            dep_source = _resolve_import_source(imp.source_path, source_import_map, source_repo)
            if not dep_source.exists():
                raise CompilerError(
                    f"Dependency '{imp.source_path}' of '{source_file}' not found (expected '{dep_source}')"
                )
            dep = _compile_file(dep_source, build_dir, source_import_map, compiled, in_progress, _key=imp.source_path)
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
