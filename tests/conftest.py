# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared pytest fixtures for the ArchML test suite."""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

# ###############
# Public Interface
# ###############


class GitRepo:
    """A throwaway local git repository usable as a remote in tests.

    Commits are fetchable by raw SHA (``uploadpack.allowAnySHA1InWant``) so the
    repository works with :func:`archml.workspace.git_ops.clone_at_commit`.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        path.mkdir(parents=True, exist_ok=True)
        _git(path, "init", "-q", str(path))
        _git(path, "config", "user.email", "test@example.com")
        _git(path, "config", "user.name", "Test")
        _git(path, "config", "commit.gpgsign", "false")
        _git(path, "config", "uploadpack.allowAnySHA1InWant", "true")

    def commit(self, files: dict[str, str], *, message: str = "commit", tag: str | None = None) -> str:
        """Write *files* (relative path -> text), commit, optionally tag; return the SHA."""
        for rel, content in files.items():
            target = self.path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        _git(self.path, "add", "-A")
        _git(self.path, "commit", "-qm", message)
        if tag is not None:
            _git(self.path, "tag", tag)
        return _git(self.path, "rev-parse", "HEAD").strip()


@pytest.fixture
def make_git_repo(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], GitRepo]:
    """Return a factory creating named :class:`GitRepo` instances in temp dirs."""

    def factory(name: str) -> GitRepo:
        return GitRepo(tmp_path_factory.mktemp(f"repo-{name}"))

    return factory


# ################
# Implementation
# ################


def _git(cwd: Path, *args: str) -> str:
    """Run a git command in *cwd* and return stdout, raising on failure."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout
