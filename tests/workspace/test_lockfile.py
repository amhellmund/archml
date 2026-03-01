# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the workspace lockfile module."""

import pytest

from archml.workspace.lockfile import (
    LOCKFILE_NAME,
    LockedRevision,
    Lockfile,
    LockfileError,
    load_lockfile,
    save_lockfile,
)

# ###############
# Public Interface
# ###############

_COMMIT_A = "a" * 40
_COMMIT_B = "b" * 40


def test_lockfile_name_constant():
    """LOCKFILE_NAME has the expected value."""
    assert LOCKFILE_NAME == ".archml-lockfile.yaml"


def test_load_empty_lockfile(tmp_path):
    """An empty YAML file is treated as an empty lockfile."""
    lf = tmp_path / LOCKFILE_NAME
    lf.write_text("", encoding="utf-8")

    lockfile = load_lockfile(lf)

    assert isinstance(lockfile, Lockfile)
    assert lockfile.locked_revisions == []


def test_load_lockfile_with_no_revisions(tmp_path):
    """A lockfile with an explicit empty list is valid."""
    lf = tmp_path / LOCKFILE_NAME
    lf.write_text("locked-revisions: []\n", encoding="utf-8")

    lockfile = load_lockfile(lf)

    assert lockfile.locked_revisions == []


def test_load_lockfile_with_single_entry(tmp_path):
    """A lockfile with one revision entry is parsed correctly."""
    lf = tmp_path / LOCKFILE_NAME
    lf.write_text(
        "locked-revisions:\n"
        f"  - name: payments\n"
        f"    git-repository: https://github.com/example/payments\n"
        f"    revision: main\n"
        f"    commit: {_COMMIT_A}\n",
        encoding="utf-8",
    )

    lockfile = load_lockfile(lf)

    assert len(lockfile.locked_revisions) == 1
    entry = lockfile.locked_revisions[0]
    assert entry.name == "payments"
    assert entry.git_repository == "https://github.com/example/payments"
    assert entry.revision == "main"
    assert entry.commit == _COMMIT_A


def test_load_lockfile_with_multiple_entries(tmp_path):
    """A lockfile with multiple revision entries is parsed correctly."""
    lf = tmp_path / LOCKFILE_NAME
    lf.write_text(
        "locked-revisions:\n"
        f"  - name: alpha\n"
        f"    git-repository: https://example.com/alpha\n"
        f"    revision: v1.0\n"
        f"    commit: {_COMMIT_A}\n"
        f"  - name: beta\n"
        f"    git-repository: https://example.com/beta\n"
        f"    revision: main\n"
        f"    commit: {_COMMIT_B}\n",
        encoding="utf-8",
    )

    lockfile = load_lockfile(lf)

    assert len(lockfile.locked_revisions) == 2
    assert lockfile.locked_revisions[0].name == "alpha"
    assert lockfile.locked_revisions[1].name == "beta"


def test_save_and_reload_lockfile(tmp_path):
    """A saved lockfile can be reloaded with identical content."""
    lf = tmp_path / LOCKFILE_NAME
    entry = LockedRevision(
        name="myrepo",
        git_repository="https://example.com/repo",
        revision="main",
        commit=_COMMIT_A,
    )
    lockfile = Lockfile(locked_revisions=[entry])

    save_lockfile(lockfile, lf)
    reloaded = load_lockfile(lf)

    assert len(reloaded.locked_revisions) == 1
    r = reloaded.locked_revisions[0]
    assert r.name == "myrepo"
    assert r.git_repository == "https://example.com/repo"
    assert r.revision == "main"
    assert r.commit == _COMMIT_A


def test_save_lockfile_sorts_entries_by_name(tmp_path):
    """Saved lockfile entries are sorted by name for reproducibility."""
    lf = tmp_path / LOCKFILE_NAME
    entries = [
        LockedRevision(name="zebra", git_repository="https://z.example.com", revision="main", commit=_COMMIT_B),
        LockedRevision(name="alpha", git_repository="https://a.example.com", revision="v1.0", commit=_COMMIT_A),
    ]
    lockfile = Lockfile(locked_revisions=entries)

    save_lockfile(lockfile, lf)
    reloaded = load_lockfile(lf)

    assert reloaded.locked_revisions[0].name == "alpha"
    assert reloaded.locked_revisions[1].name == "zebra"


def test_save_lockfile_uses_aliases_in_yaml(tmp_path):
    """The saved YAML file uses hyphenated aliases (e.g., 'git-repository')."""
    lf = tmp_path / LOCKFILE_NAME
    lockfile = Lockfile(
        locked_revisions=[
            LockedRevision(name="repo", git_repository="https://example.com", revision="main", commit=_COMMIT_A)
        ]
    )

    save_lockfile(lockfile, lf)
    content = lf.read_text(encoding="utf-8")

    assert "git-repository:" in content
    assert "locked-revisions:" in content
    assert "git_repository:" not in content


def test_load_lockfile_file_not_found(tmp_path):
    """Loading a nonexistent lockfile raises LockfileError."""
    missing = tmp_path / "no-such-file.yaml"

    with pytest.raises(LockfileError, match="Cannot read lockfile"):
        load_lockfile(missing)


def test_load_lockfile_invalid_yaml(tmp_path):
    """A lockfile with invalid YAML raises LockfileError."""
    lf = tmp_path / LOCKFILE_NAME
    lf.write_text("locked-revisions: [\nbad yaml", encoding="utf-8")

    with pytest.raises(LockfileError, match="Invalid YAML"):
        load_lockfile(lf)


def test_load_lockfile_missing_required_field(tmp_path):
    """A lockfile entry missing a required field raises LockfileError."""
    lf = tmp_path / LOCKFILE_NAME
    lf.write_text(
        "locked-revisions:\n  - name: incomplete\n    git-repository: https://example.com\n    revision: main\n",
        # missing 'commit' field
        encoding="utf-8",
    )

    with pytest.raises(LockfileError, match="Invalid lockfile"):
        load_lockfile(lf)


def test_load_lockfile_unknown_field(tmp_path):
    """A lockfile entry with an unexpected field raises LockfileError."""
    lf = tmp_path / LOCKFILE_NAME
    lf.write_text(
        f"locked-revisions:\n"
        f"  - name: repo\n"
        f"    git-repository: https://example.com\n"
        f"    revision: main\n"
        f"    commit: {_COMMIT_A}\n"
        f"    extra-field: bad\n",
        encoding="utf-8",
    )

    with pytest.raises(LockfileError, match="Invalid lockfile"):
        load_lockfile(lf)


def test_locked_revision_tag_revision(tmp_path):
    """A LockedRevision with a tag revision is valid."""
    lf = tmp_path / LOCKFILE_NAME
    lf.write_text(
        f"locked-revisions:\n"
        f"  - name: lib\n"
        f"    git-repository: https://example.com/lib\n"
        f"    revision: v2.1.0\n"
        f"    commit: {_COMMIT_A}\n",
        encoding="utf-8",
    )

    lockfile = load_lockfile(lf)

    assert lockfile.locked_revisions[0].revision == "v2.1.0"


def test_locked_revision_commit_hash_revision(tmp_path):
    """A LockedRevision with a commit hash as revision is valid."""
    lf = tmp_path / LOCKFILE_NAME
    lf.write_text(
        f"locked-revisions:\n"
        f"  - name: lib\n"
        f"    git-repository: https://example.com/lib\n"
        f"    revision: {_COMMIT_A}\n"
        f"    commit: {_COMMIT_A}\n",
        encoding="utf-8",
    )

    lockfile = load_lockfile(lf)

    assert lockfile.locked_revisions[0].revision == _COMMIT_A
    assert lockfile.locked_revisions[0].commit == _COMMIT_A
