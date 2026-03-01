# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Incremental compiler workflow for .archml files.

Implements a CMake-style cache: an artifact is reused when it already exists
and is strictly newer than the corresponding source file.  Dependencies are
compiled recursively before the dependent file is validated.

Two forms of cross-file import are supported:

* **Local workspace imports** — ``from mnemonic/path/to/file import …``
  The first path segment is looked up as a mnemonic in the caller-supplied
  *source_import_map* (``{mnemonic: absolute_base_path}``), derived from the
  workspace ``source-imports`` configuration.

* **Remote git imports** — ``from @repo/path/to/file import …``
  The ``@repo`` prefix identifies a named Git repository configured in the
  workspace.  The caller-supplied *source_import_map* must contain an entry
  keyed as ``"@repo"`` pointing to the locally synced directory (populated by
  ``archml sync-remote``).  If the key is absent, :class:`CompilerError` is
  raised with a message directing the user to run ``archml sync-remote``.

* **Remote git imports with mnemonics** — ``from @repo/mnemonic/path/to/file import …``
  When the remote repository defines its own ``source-imports`` in its
  ``.archml-workspace.yaml``, those mnemonics are exposed as two-segment keys
  ``"@repo/mnemonic"`` in *source_import_map*.  Resolution tries the
  two-segment key before falling back to the bare ``"@repo"`` key so that
  mnemonic-rooted paths take precedence over literal subdirectory paths in the
  repository root.
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
    source_import_map: dict[str, Path],
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
        source_import_map: Mapping from mnemonic names to absolute base paths.
            The empty-string key ``""`` represents the workspace root (used to
            resolve non-mnemonic imports and compute artifact keys for files
            that do not belong to a named mnemonic).  Import paths of the form
            ``mnemonic/rel`` are resolved by looking up *mnemonic* in this map
            and appending *rel*.

    Returns:
        A mapping from canonical path keys (e.g. ``"shared/types"`` or
        ``"common/types"``) to their compiled :class:`~archml.model.entities.ArchFile`
        models.

    Raises:
        CompilerError: On parse errors, missing imports, unsupported remote
            imports, semantic errors, or circular dependencies.
    """
    compiled: dict[str, ArchFile] = {}
    in_progress: set[str] = set()
    for f in files:
        # For top-level files, compute the key from the filesystem path.
        # Dependency keys are always the import path string (passed via _key).
        _compile_file(f, build_dir, source_import_map, compiled, in_progress)
    return compiled


# ################
# Implementation
# ################


def _rel_key(source_file: Path, source_import_map: dict[str, Path]) -> str:
    """Return the canonical key for a source file (path without extension).

    For files under the workspace root (``source_import_map[""]``), the key is
    the relative path without the ``.archml`` suffix (e.g. ``"shared/types"``).

    For files under a named mnemonic base path, the key is ``"mnemonic/rel"``
    (e.g. ``"common/types"``).

    Raises:
        CompilerError: If the file is not under any configured base path.
    """
    # Try the workspace root (empty-string key) first — its key has no prefix.
    workspace_root = source_import_map.get("")
    if workspace_root is not None:
        try:
            rel = source_file.relative_to(workspace_root)
            return str(rel.with_suffix("")).replace("\\", "/")
        except ValueError:
            pass

    for mnemonic, base_path in source_import_map.items():
        if mnemonic == "":
            continue
        try:
            rel = source_file.relative_to(base_path)
            return f"{mnemonic}/" + str(rel.with_suffix("")).replace("\\", "/")
        except ValueError:
            continue

    raise CompilerError(f"Source file '{source_file}' is not under any configured source import base path")


def _artifact_path(key: str, build_dir: Path) -> Path:
    """Return the artifact path for a given canonical key.

    The key segments (split on ``/``) map directly to subdirectory components
    under *build_dir* (e.g. ``"common/types"`` → ``build_dir/common/types.archml.json``).
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
    source_import_map: dict[str, Path],
) -> Path:
    """Resolve an import path to the absolute path of the ``.archml`` source file.

    Args:
        import_path: The raw import path string as stored in :class:`ImportDeclaration`
            (e.g. ``"shared/types"``, ``"common/types"``, ``"@repo/path/to/file"``,
            or ``"@repo/mnemonic/path/to/file"``).
        source_import_map: Mapping from mnemonic names to base paths.  The
            empty-string key ``""`` is the workspace root used for
            non-mnemonic imports.  Remote repositories are keyed as ``"@repo"``
            and their mnemonics as ``"@repo/mnemonic"``.

    Returns:
        Absolute path to the ``.archml`` file (which may or may not exist).

    Raises:
        CompilerError: If *import_path* is a remote git import (starts with
            ``@``) whose repository key is absent from *source_import_map*.
    """
    if import_path.startswith("@"):
        slash_pos = import_path.find("/", 1)
        if slash_pos == -1:
            raise CompilerError(
                f"Invalid remote git import path '{import_path}': expected '@repo/path/to/file'"
            )
        # Try a two-segment key (@repo/mnemonic) first so that remote-repo
        # mnemonics take precedence over literal subdirectory paths.
        second_slash = import_path.find("/", slash_pos + 1)
        if second_slash != -1:
            two_seg_key = import_path[:second_slash]  # e.g. "@payments/utils"
            if two_seg_key in source_import_map:
                rel = import_path[second_slash + 1 :]
                return source_import_map[two_seg_key] / (rel + ".archml")
        repo_key = import_path[:slash_pos]
        if repo_key not in source_import_map:
            raise CompilerError(
                f"Remote git import '{import_path}': repository '{repo_key}' not found in workspace. "
                "Run 'archml sync-remote' to download remote repositories."
            )
        rel = import_path[slash_pos + 1 :]
        return source_import_map[repo_key] / (rel + ".archml")
    slash_pos = import_path.find("/")
    if slash_pos != -1:
        first_segment = import_path[:slash_pos]
        if first_segment in source_import_map:
            rel = import_path[slash_pos + 1 :]
            return source_import_map[first_segment] / (rel + ".archml")
    workspace_root = source_import_map.get("")
    if workspace_root is None:
        raise CompilerError(f"Cannot resolve import '{import_path}': no workspace root configured in source_import_map")
    return workspace_root / (import_path + ".archml")


def _compile_file(
    source_file: Path,
    build_dir: Path,
    source_import_map: dict[str, Path],
    compiled: dict[str, ArchFile],
    in_progress: set[str],
    *,
    _key: str | None = None,
) -> ArchFile:
    """Compile one .archml file, recursively compiling its dependencies first.

    Args:
        source_file: Absolute path to the .archml file to compile.
        build_dir: Root directory for compiled artifacts.
        source_import_map: Mapping from mnemonic names to base paths for
            cross-workspace import resolution.  The empty-string key ``""``
            is the workspace root.
        compiled: Accumulator mapping already-compiled canonical keys to models.
        in_progress: Set of canonical keys currently being compiled (cycle guard).
        _key: Optional pre-computed canonical key. When provided (always the case
            for dependency files resolved via ``_resolve_import_source``), the key
            is used directly without inferring it from the filesystem path. This
            prevents ambiguity when a mnemonic base path is nested inside the
            workspace root.

    Returns:
        The compiled :class:`~archml.model.entities.ArchFile` for *source_file*.

    Raises:
        CompilerError: On any compilation failure.
    """
    key = _key if _key is not None else _rel_key(source_file, source_import_map)

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
                dep_source = _resolve_import_source(imp.source_path, source_import_map)
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
                dep_source = _resolve_import_source(imp.source_path, source_import_map)
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
            dep_source = _resolve_import_source(imp.source_path, source_import_map)
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
