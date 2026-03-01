# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Lockfile model for pinning remote git repository commits."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# ###############
# Public Interface
# ###############

LOCKFILE_NAME = ".archml-lockfile.yaml"


class LockfileError(Exception):
    """Raised when the lockfile cannot be read, written, or is invalid."""


class LockedRevision(BaseModel):
    """A pinned commit entry for a remote git repository."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    git_repository: str = Field(alias="git-repository")
    revision: str
    commit: str


class Lockfile(BaseModel):
    """Top-level lockfile model storing all pinned git repository commits."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    locked_revisions: list[LockedRevision] = Field(alias="locked-revisions", default_factory=list)


def load_lockfile(path: Path) -> Lockfile:
    """Load and validate the lockfile from disk.

    An empty or missing-content file is treated as an empty lockfile.

    Args:
        path: Path to the .archml-lockfile.yaml file.

    Returns:
        A validated Lockfile instance.

    Raises:
        LockfileError: If the file cannot be read, contains invalid YAML,
            or does not conform to the expected schema.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LockfileError(f"Cannot read lockfile '{path}': {exc}") from exc

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise LockfileError(f"Invalid YAML in lockfile '{path}': {exc}") from exc

    if data is None:
        data = {}

    try:
        return Lockfile.model_validate(data)
    except ValidationError as exc:
        raise LockfileError(f"Invalid lockfile '{path}': {exc}") from exc


def save_lockfile(lockfile: Lockfile, path: Path) -> None:
    """Save the lockfile to disk.

    Revisions are sorted by name for reproducible output.

    Args:
        lockfile: The lockfile to serialize.
        path: Destination path for the lockfile.

    Raises:
        LockfileError: If the file cannot be written.
    """
    data = lockfile.model_dump(by_alias=True)
    data["locked-revisions"].sort(key=lambda x: x["name"])
    try:
        path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        raise LockfileError(f"Cannot write lockfile '{path}': {exc}") from exc
