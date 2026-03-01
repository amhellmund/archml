# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Workspace configuration loading and data models."""

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# ###############
# Public Interface
# ###############

_MNEMONIC_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class WorkspaceConfigError(Exception):
    """Raised when the workspace configuration file is invalid or unreadable."""


class LocalPathImport(BaseModel):
    """A source import resolved from a local directory relative to the workspace."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    local_path: str = Field(alias="local-path")

    @field_validator("name")
    @classmethod
    def validate_mnemonic_name(cls, v: str) -> str:
        """Validate mnemonic: lowercase letter, then alphanumeric/dash/underscore."""
        if not _MNEMONIC_RE.match(v):
            raise ValueError(
                f"Invalid mnemonic name '{v}': must start with a lowercase letter "
                "followed by lowercase letters, digits, hyphens, or underscores (no slashes)"
            )
        return v


class GitPathImport(BaseModel):
    """A source import resolved from a git repository."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    git_repository: str = Field(alias="git-repository")
    revision: str

    @field_validator("name")
    @classmethod
    def validate_mnemonic_name(cls, v: str) -> str:
        """Validate repo name: lowercase letter, then alphanumeric/dash/underscore."""
        if not _MNEMONIC_RE.match(v):
            raise ValueError(
                f"Invalid repo name '{v}': must start with a lowercase letter "
                "followed by lowercase letters, digits, hyphens, or underscores (no slashes)"
            )
        return v


SourceImport = LocalPathImport | GitPathImport


class WorkspaceConfig(BaseModel):
    """Top-level workspace configuration parsed from .archml-workspace.yaml."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    build_directory: str = Field(alias="build-directory")
    remote_sync_directory: str = Field(alias="remote-sync-directory", default=".archml-remotes")
    source_imports: list[LocalPathImport | GitPathImport] = Field(
        alias="source-imports",
        min_length=1,
    )


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
