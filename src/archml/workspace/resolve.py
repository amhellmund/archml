# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Transitive resolution of remote workspace dependencies.

Walks the graph of git imports breadth-first, materialising each referenced
workspace, detecting version conflicts (the diamond problem) and building the
alias map the compiler needs to unify shared dependencies.
"""

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from posixpath import normpath

from archml.workspace.config import (
    WORKSPACE_CONFIG_FILENAME,
    GitPathImport,
    WorkspaceConfig,
    WorkspaceConfigError,
    load_workspace_config,
)
from archml.workspace.git_ops import GitError, clone_at_commit, get_current_commit, resolve_commit

# ###############
# Public Interface
# ###############


class DependencyResolutionError(Exception):
    """Raised when the remote dependency graph cannot be resolved."""


class DependencyConflictError(DependencyResolutionError):
    """Raised when the same repository workspace is required at differing commits."""


@dataclass(frozen=True)
class ResolvedRepo:
    """One resolved workspace in the transitive closure.

    *identity* is the canonical workspace name declared by the imported
    workspace; it is shared by every importer that reaches this same resolved
    reference, which is what lets the compiler unify the dependency.
    """

    identity: str
    git_repository: str
    revision: str
    commit: str
    path: str


@dataclass
class ResolvedClosure:
    """The full transitive closure plus the alias map for the compiler."""

    repos: list[ResolvedRepo] = field(default_factory=list)
    """One :class:`ResolvedRepo` per distinct resolved reference, ordered by discovery."""

    alias_map: dict[tuple[str, str], str] = field(default_factory=dict)
    """``(importer_repo_id, alias) -> "@identity"`` for every git import edge."""


def normalize_url(url: str) -> str:
    """Return a canonical form of a git URL for identity comparison.

    Strips surrounding whitespace, a trailing slash, and a trailing ``.git``
    so that equivalent URLs collapse to the same key.
    """
    u = url.strip()
    if u.endswith("/"):
        u = u[:-1]
    if u.endswith(".git"):
        u = u[:-4]
    return u


def normalize_path(path: str) -> str:
    """Return a canonical repo-relative workspace path (``"."`` for the root)."""
    return normpath(path.strip() or ".")


def resolve_closure(root_config: WorkspaceConfig, sync_dir: Path) -> ResolvedClosure:
    """Resolve the transitive closure of remote workspace dependencies.

    Performs a breadth-first walk over git imports starting from *root_config*.
    Each referenced workspace is fetched at its resolved commit into
    ``sync_dir/<identity>``.  Conflicts are detected per resolved reference
    ``(normalized url, path)``: if two importers require the same reference at
    different commits a :class:`DependencyConflictError` is raised.

    Args:
        root_config: The root workspace configuration.
        sync_dir: Directory under which resolved repositories are materialised.

    Returns:
        A :class:`ResolvedClosure` with the resolved repositories and the alias
        map for :func:`archml.compiler.build.compile_files`.

    Raises:
        DependencyConflictError: On conflicting commits for the same reference.
        DependencyResolutionError: On a missing nested workspace, a workspace
            identity collision, or an underlying git/config failure.
    """
    closure = ResolvedClosure()
    # ref key (normalized url, normalized path) -> ResolvedRepo
    resolved: dict[tuple[str, str], ResolvedRepo] = {}
    # identity -> ref key, to detect two distinct references claiming one name
    identity_refs: dict[str, tuple[str, str]] = {}
    # ref key -> requirers, for conflict diagnostics
    requirers: dict[tuple[str, str], list[_Requirer]] = {}

    queue: list[tuple[str, GitPathImport]] = [(root_config.name, imp) for imp in _git_imports(root_config)]

    while queue:
        importer_id, imp = queue.pop(0)
        norm_url = normalize_url(imp.git_repository)
        norm_path = normalize_path(imp.path)
        ref_key = (norm_url, norm_path)

        commit = _resolve(imp.git_repository, imp.revision)
        requirers.setdefault(ref_key, []).append(_Requirer(importer_id, imp.revision, commit))

        existing = resolved.get(ref_key)
        if existing is not None:
            if existing.commit != commit:
                raise DependencyConflictError(_conflict_message(imp.git_repository, norm_path, requirers[ref_key]))
            # Same reference, same commit: just record the alias edge.
            closure.alias_map[(importer_id, imp.name)] = f"@{existing.identity}"
            continue

        nested_config = _fetch_workspace(imp.git_repository, commit, norm_path, sync_dir)
        identity = nested_config.name

        prior = identity_refs.get(identity)
        if prior is not None and prior != ref_key:
            raise DependencyResolutionError(
                f"Workspace identity '{identity}' is claimed by two different references: "
                f"{prior[0]} (path '{prior[1]}') and {norm_url} (path '{norm_path}'). "
                "Imported workspaces must have unique names."
            )

        repo = ResolvedRepo(
            identity=identity,
            git_repository=imp.git_repository,
            revision=imp.revision,
            commit=commit,
            path=norm_path,
        )
        resolved[ref_key] = repo
        identity_refs[identity] = ref_key
        closure.repos.append(repo)
        closure.alias_map[(importer_id, imp.name)] = f"@{identity}"

        for nested_imp in _git_imports(nested_config):
            queue.append((f"@{identity}", nested_imp))

    return closure


def build_alias_map(
    root_config: WorkspaceConfig,
    sync_dir: Path,
    closure: list[ResolvedRepo],
) -> dict[tuple[str, str], str]:
    """Reconstruct the compiler alias map from an already-resolved closure.

    Maps ``(importer_repo_id, alias) -> "@identity"`` for the root workspace and
    every resolved workspace in *closure*, so that a locally chosen import alias
    resolves to the canonical workspace identity.  This mirrors what
    :func:`resolve_closure` records, but is rebuilt at compile time from the
    lockfile closure without any network access.

    Args:
        root_config: The root workspace configuration.
        sync_dir: Directory under which resolved repositories were materialised.
        closure: Resolved repositories (typically rebuilt from the lockfile).

    Returns:
        The ``(importer_repo_id, alias) -> "@identity"`` mapping.
    """
    ref_to_identity = {
        (normalize_url(repo.git_repository), normalize_path(repo.path)): repo.identity for repo in closure
    }

    alias_map: dict[tuple[str, str], str] = {}

    def _register(importer_id: str, config: WorkspaceConfig) -> None:
        for imp in _git_imports(config):
            ref = (normalize_url(imp.git_repository), normalize_path(imp.path))
            identity = ref_to_identity.get(ref)
            if identity is not None:
                alias_map[(importer_id, imp.name)] = f"@{identity}"

    _register(root_config.name, root_config)
    for repo in closure:
        workspace_yaml = sync_dir / repo.identity / repo.path / WORKSPACE_CONFIG_FILENAME
        if not workspace_yaml.exists():
            continue
        try:
            _register(f"@{repo.identity}", load_workspace_config(workspace_yaml))
        except WorkspaceConfigError:
            continue

    return alias_map


# ################
# Implementation
# ################


@dataclass(frozen=True)
class _Requirer:
    """An importer that requires a particular resolved reference."""

    importer_id: str
    revision: str
    commit: str


def _git_imports(config: WorkspaceConfig) -> list[GitPathImport]:
    """Return the git imports of *config* in declaration order."""
    return [imp for imp in config.source_imports if isinstance(imp, GitPathImport)]


def _resolve(url: str, revision: str) -> str:
    """Resolve *revision* to a commit SHA, wrapping git failures."""
    try:
        return resolve_commit(url, revision)
    except GitError as exc:
        raise DependencyResolutionError(f"Failed to resolve '{revision}' in '{url}': {exc}") from exc


def _fetch_workspace(url: str, commit: str, norm_path: str, sync_dir: Path) -> WorkspaceConfig:
    """Materialise the repository at *commit* and load its nested workspace.

    The repository is checked out under ``sync_dir/<identity>`` where
    *identity* is the nested workspace's ``name:``.  Because the identity is
    only known after checkout, the repository is first cloned into a temporary
    sibling directory; once the name is known the checkout is moved into place
    (or discarded if an up-to-date checkout already exists).
    """
    sync_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".tmp-clone-", dir=sync_dir))
    try:
        try:
            clone_at_commit(url, commit, tmp)
        except GitError as exc:
            raise DependencyResolutionError(f"Failed to fetch '{url}' at {commit[:8]}: {exc}") from exc

        workspace_yaml = tmp / norm_path / WORKSPACE_CONFIG_FILENAME
        if not workspace_yaml.exists():
            raise DependencyResolutionError(
                f"No {WORKSPACE_CONFIG_FILENAME} found at path '{norm_path}' in '{url}' at {commit[:8]}"
            )
        try:
            config = load_workspace_config(workspace_yaml)
        except WorkspaceConfigError as exc:
            raise DependencyResolutionError(f"Invalid workspace in '{url}' at path '{norm_path}': {exc}") from exc

        dest = sync_dir / config.name
        if get_current_commit(dest) == commit:
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            if dest.exists():
                shutil.rmtree(dest)
            tmp.replace(dest)
        return config
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def _conflict_message(url: str, norm_path: str, requirers: list[_Requirer]) -> str:
    """Build a readable diamond-conflict error message."""
    location = f"repository '{url}'" + (f" (path '{norm_path}')" if norm_path != "." else "")
    lines = [f"Dependency conflict for {location}:"]
    for req in requirers:
        lines.append(f"  - required by '{req.importer_id}' at revision '{req.revision}' -> commit {req.commit[:8]}")
    return "\n".join(lines)
