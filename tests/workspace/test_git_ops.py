# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the git operations module."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from archml.workspace.git_ops import (
    GitError,
    clone_at_commit,
    get_current_commit,
    is_commit_hash,
    resolve_commit,
)

# ###############
# Public Interface
# ###############

_COMMIT = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
_COMMIT_B = "b" * 40
_REPO_URL = "https://github.com/example/repo"


class TestIsCommitHash:
    def test_returns_true_for_40_hex_chars(self):
        """A 40-character lowercase hex string is a valid commit hash."""
        assert is_commit_hash("a" * 40) is True

    def test_returns_true_for_mixed_hex(self):
        """40 hex characters with letters a-f are valid."""
        assert is_commit_hash(_COMMIT) is True

    def test_returns_false_for_short_string(self):
        """A string shorter than 40 characters is not a commit hash."""
        assert is_commit_hash("abc123") is False

    def test_returns_false_for_long_string(self):
        """A string longer than 40 characters is not a commit hash."""
        assert is_commit_hash("a" * 41) is False

    def test_returns_false_for_non_hex_chars(self):
        """A string with non-hex characters (e.g., g-z) is not a commit hash."""
        assert is_commit_hash("g" * 40) is False

    def test_returns_false_for_uppercase(self):
        """Uppercase hex letters are not accepted (git uses lowercase)."""
        assert is_commit_hash("A" * 40) is False

    def test_returns_false_for_empty_string(self):
        """An empty string is not a commit hash."""
        assert is_commit_hash("") is False

    def test_returns_false_for_branch_name(self):
        """A branch name like 'main' is not a commit hash."""
        assert is_commit_hash("main") is False

    def test_returns_false_for_tag(self):
        """A tag like 'v1.0.0' is not a commit hash."""
        assert is_commit_hash("v1.0.0") is False


class TestResolveCommit:
    def test_returns_hash_directly_without_network(self):
        """A 40-char commit hash is returned as-is without calling git."""
        with patch("subprocess.run") as mock_run:
            result = resolve_commit(_REPO_URL, _COMMIT)
        assert result == _COMMIT
        mock_run.assert_not_called()

    def test_resolves_branch_via_ls_remote(self):
        """A branch name is resolved by calling git ls-remote."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"{_COMMIT}\trefs/heads/main\n"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = resolve_commit(_REPO_URL, "main")

        assert result == _COMMIT
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "ls-remote" in call_args
        assert "refs/heads/main" in call_args

    def test_resolves_tag_via_ls_remote(self):
        """A tag name is resolved by calling git ls-remote."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"{_COMMIT}\trefs/tags/v1.0\n"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = resolve_commit(_REPO_URL, "v1.0")

        assert result == _COMMIT

    def test_raises_if_revision_not_found(self):
        """GitError is raised if ls-remote returns no output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(GitError, match="not found"):
                resolve_commit(_REPO_URL, "nonexistent-branch")

    def test_raises_if_ls_remote_fails(self):
        """GitError is raised if git ls-remote exits with non-zero."""
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        mock_result.stderr = "fatal: repository not found"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(GitError, match="Failed to query remote"):
                resolve_commit(_REPO_URL, "main")

    def test_raises_if_git_not_found(self):
        """GitError is raised if the git executable is not on PATH."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(GitError, match="git executable not found"):
                resolve_commit(_REPO_URL, "main")

    def test_raises_on_timeout(self):
        """GitError is raised if git ls-remote times out."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=60)):
            with pytest.raises(GitError, match="timed out"):
                resolve_commit(_REPO_URL, "main")

    def test_raises_if_commit_in_output_is_malformed(self):
        """GitError is raised if ls-remote output has an unexpected format."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not-a-hash\trefs/heads/main\n"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(GitError, match="Unexpected output"):
                resolve_commit(_REPO_URL, "main")

    def test_uses_first_line_when_multiple_refs(self):
        """When multiple refs match, the commit from the first line is returned."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"{_COMMIT}\trefs/heads/v1.0\n{_COMMIT_B}\trefs/tags/v1.0\n"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = resolve_commit(_REPO_URL, "v1.0")

        assert result == _COMMIT


class TestCloneAtCommit:
    def test_runs_git_init_remote_fetch_checkout(self, tmp_path: Path):
        """clone_at_commit runs git init, remote add, fetch, and checkout."""
        target = tmp_path / "repo"
        successful = MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", return_value=successful) as mock_run:
            clone_at_commit(_REPO_URL, _COMMIT, target)

        calls = mock_run.call_args_list
        # Verify sequence: init, remote add, fetch, checkout
        assert any("init" in str(c) for c in calls)
        assert any("remote" in str(c) and "add" in str(c) for c in calls)
        assert any("fetch" in str(c) for c in calls)
        assert any("checkout" in str(c) for c in calls)

    def test_removes_existing_directory_before_clone(self, tmp_path: Path):
        """An existing target directory is removed before cloning."""
        target = tmp_path / "repo"
        target.mkdir()
        (target / "existing_file.txt").write_text("old content")

        successful = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=successful):
            clone_at_commit(_REPO_URL, _COMMIT, target)

        # The existing file should have been removed (directory was re-created by git init)
        assert not (target / "existing_file.txt").exists()

    def test_cleans_up_on_failure(self, tmp_path: Path):
        """The target directory is removed if any git step fails."""
        target = tmp_path / "repo"

        def side_effect(cmd, **kwargs):
            if "init" in cmd:
                target.mkdir(parents=True, exist_ok=True)
                return MagicMock(returncode=0, stdout="", stderr="")
            if "remote" in cmd:
                return MagicMock(returncode=128, stdout="", stderr="fatal: error")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=side_effect):
            with pytest.raises(GitError):
                clone_at_commit(_REPO_URL, _COMMIT, target)

        assert not target.exists()

    def test_raises_git_error_on_fetch_failure(self, tmp_path: Path):
        """GitError is raised when the fetch step fails."""
        target = tmp_path / "repo"

        call_count = 0

        def side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # init and remote add succeed
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=128, stdout="", stderr="fatal: couldn't find remote ref")

        with patch("subprocess.run", side_effect=side_effect):
            with pytest.raises(GitError):
                clone_at_commit(_REPO_URL, _COMMIT, target)

    def test_raises_if_git_not_found(self, tmp_path: Path):
        """GitError is raised if git is not on PATH."""
        target = tmp_path / "repo"

        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(GitError, match="git executable not found"):
                clone_at_commit(_REPO_URL, _COMMIT, target)


class TestGetCurrentCommit:
    def test_returns_commit_for_valid_repo(self, tmp_path: Path):
        """Returns the HEAD commit SHA for a valid repo directory."""
        repo_dir = tmp_path / "repo"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"{_COMMIT}\n"

        with patch("subprocess.run", return_value=mock_result):
            result = get_current_commit(repo_dir)

        assert result == _COMMIT

    def test_returns_none_for_non_git_directory(self, tmp_path: Path):
        """Returns None when the directory is not a git repository."""
        repo_dir = tmp_path / "not-a-repo"
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            result = get_current_commit(repo_dir)

        assert result is None

    def test_returns_none_for_nonexistent_directory(self, tmp_path: Path):
        """Returns None when the directory does not exist."""
        repo_dir = tmp_path / "missing"
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            result = get_current_commit(repo_dir)

        assert result is None

    def test_returns_none_for_malformed_output(self, tmp_path: Path):
        """Returns None if git output is not a valid commit hash."""
        repo_dir = tmp_path / "repo"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not-a-hash\n"

        with patch("subprocess.run", return_value=mock_result):
            result = get_current_commit(repo_dir)

        assert result is None

    def test_raises_if_git_not_found(self, tmp_path: Path):
        """GitError is raised if the git executable is not on PATH."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(GitError, match="git executable not found"):
                get_current_commit(tmp_path)

    def test_passes_repo_dir_to_git_c_flag(self, tmp_path: Path):
        """The directory is passed using the -C flag to git."""
        repo_dir = tmp_path / "myrepo"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"{_COMMIT}\n"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            get_current_commit(repo_dir)

        call_args = mock_run.call_args[0][0]
        assert "-C" in call_args
        assert str(repo_dir) in call_args
