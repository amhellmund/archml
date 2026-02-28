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
    source_imports: list[LocalPathImport | GitPathImport] = Field(alias="source-imports", default_factory=list)


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
