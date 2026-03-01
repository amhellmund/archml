# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Git operations for remote repository management."""

import re
import shutil
import subprocess
from pathlib import Path

# ###############
# Public Interface
# ###############

_COMMIT_HASH_RE = re.compile(r"^[0-9a-f]{40}$")


class GitError(Exception):
    """Raised when a git operation fails."""


def is_commit_hash(revision: str) -> bool:
    """Return True if *revision* is a full 40-character hexadecimal commit SHA."""
    return bool(_COMMIT_HASH_RE.match(revision))


def resolve_commit(url: str, revision: str) -> str:
    """Resolve a branch name, tag, or commit hash to a full commit SHA.

    If *revision* already looks like a full 40-character commit SHA, it is
    returned as-is without any network access.  Otherwise, ``git ls-remote``
    is used to query the remote repository.

    Args:
        url: URL of the remote git repository.
        revision: Branch name, tag name, or full commit SHA to resolve.

    Returns:
        A 40-character hexadecimal commit SHA.

    Raises:
        GitError: If the revision cannot be resolved, git is not available,
            or a network or remote error occurs.
    """
    if is_commit_hash(revision):
        return revision

    result = _run_git_raw(
        ["ls-remote", url, f"refs/heads/{revision}", f"refs/tags/{revision}"],
        timeout=60,
    )
    if result.returncode != 0:
        raise GitError(f"Failed to query remote '{url}': {result.stderr.strip()}")

    lines = result.stdout.strip().splitlines()
    if not lines:
        raise GitError(f"Revision '{revision}' not found in '{url}'")

    commit = lines[0].split()[0]
    if not is_commit_hash(commit):
        raise GitError(f"Unexpected output from git ls-remote: {lines[0]!r}")

    return commit


def clone_at_commit(url: str, commit: str, target_dir: Path) -> None:
    """Clone a remote git repository at a specific commit without history.

    Any existing content at *target_dir* is removed before cloning.  On
    failure, any partially created *target_dir* is cleaned up.

    Args:
        url: URL of the remote git repository.
        commit: Full 40-character commit SHA to check out.
        target_dir: Local directory to clone into (will be created).

    Raises:
        GitError: If any git operation fails.
    """
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    try:
        _run_git(["init", str(target_dir)])
        _run_git(["-C", str(target_dir), "remote", "add", "origin", url])
        _run_git(["-C", str(target_dir), "fetch", "--depth=1", "origin", commit])
        _run_git(["-C", str(target_dir), "checkout", "FETCH_HEAD"])
    except GitError:
        if target_dir.exists():
            shutil.rmtree(target_dir)
        raise


def get_current_commit(target_dir: Path) -> str | None:
    """Return the HEAD commit SHA of a cloned repository, or None if unavailable.

    Args:
        target_dir: Path to a locally cloned repository.

    Returns:
        A 40-character commit SHA, or None if *target_dir* is not a valid git
        repository or the HEAD cannot be determined.

    Raises:
        GitError: If git is not available on the system.
    """
    result = _run_git_raw(["-C", str(target_dir), "rev-parse", "HEAD"], timeout=10)
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit if is_commit_hash(commit) else None


# ################
# Implementation
# ################


def _run_git_raw(args: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the raw CompletedProcess result.

    Raises:
        GitError: If git is not found on PATH or the command times out.
    """
    try:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"Git command timed out: git {' '.join(args)}") from exc


def _run_git(args: list[str], *, timeout: int = 120) -> str:
    """Run a git command and return stdout, raising GitError on non-zero exit.

    Raises:
        GitError: If git is not found, times out, or exits with a non-zero code.
    """
    result = _run_git_raw(args, timeout=timeout)
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout
