# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Workspace configuration loading and data models."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# ###############
# Public Interface
# ###############


class WorkspaceConfigError(Exception):
    """Raised when the workspace configuration file is invalid or unreadable."""


class LocalPathImport(BaseModel):
    """A source import resolved from a local directory relative to the workspace."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    local_path: str = Field(alias="local-path")


class GitPathImport(BaseModel):
    """A source import resolved from a git repository."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    git_repository: str = Field(alias="git-repository")
    revision: str


SourceImport = LocalPathImport | GitPathImport


class WorkspaceConfig(BaseModel):
    """Top-level workspace configuration parsed from .archml-workspace.yaml."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    build_directory: str = Field(alias="build-directory")
    remote_sync_directory: str = Field(alias="remote-sync-directory", default=".archml-remotes")
    source_imports: list[LocalPathImport | GitPathImport] = Field(alias="source-imports", default_factory=list)


WORKSPACE_CONFIG_FILENAME = ".archml-workspace.yaml"


def find_workspace_root(start_dir: Path) -> Path | None:
    """Walk up the directory tree to find the ArchML workspace root.

    Searches for a .archml-workspace.yaml file starting from start_dir and
    ascending through parent directories until the filesystem root is reached.

    Args:
        start_dir: Directory to start the search from.

    Returns:
        The directory containing .archml-workspace.yaml, or None if not found.
    """
    current = start_dir.resolve()
    while True:
        if (current / WORKSPACE_CONFIG_FILENAME).exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def load_workspace_config(path: Path) -> WorkspaceConfig:
    """Load and validate a workspace configuration file.

    Args:
        path: Path to the .archml-workspace.yaml file.

    Returns:
        A validated WorkspaceConfig instance.

    Raises:
        WorkspaceConfigError: If the file cannot be read, is not valid YAML,
            or does not conform to the expected schema.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorkspaceConfigError(f"Cannot read workspace config '{path}': {exc}") from exc

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise WorkspaceConfigError(f"Invalid YAML in workspace config '{path}': {exc}") from exc

    try:
        return WorkspaceConfig.model_validate(data)
    except ValidationError as exc:
        raise WorkspaceConfigError(f"Invalid workspace config '{path}': {exc}") from exc
