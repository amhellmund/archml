# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Data model and YAML parser for the ArchML workspace configuration file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# ###############
# Public Interface
# ###############


class WorkspaceConfigError(Exception):
    """Raised when a workspace configuration file is invalid or cannot be loaded."""


@dataclass
class LocalPathImport:
    """A source import resolved via a local path relative to the workspace root."""

    name: str
    local_path: str


@dataclass
class GitPathImport:
    """A source import resolved via a remote Git repository."""

    name: str
    git_repository: str
    revision: str


SourceImport = LocalPathImport | GitPathImport


@dataclass
class WorkspaceConfig:
    """The parsed configuration for an ArchML workspace.

    Attributes:
        build_directory: Relative path (from the workspace root) for compiler output.
        source_imports: Named import mappings used by the import system.
    """

    build_directory: str
    source_imports: list[SourceImport] = field(default_factory=list)


def load_workspace_config(path: Path) -> WorkspaceConfig:
    """Load and parse an ArchML workspace configuration file.

    Args:
        path: Path to the `.archml-workspace.yaml` file.

    Returns:
        A WorkspaceConfig instance populated from the file.

    Raises:
        WorkspaceConfigError: If the file cannot be read or the configuration is invalid.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise WorkspaceConfigError(f"Workspace config file not found: {path}") from None
    except OSError as exc:
        raise WorkspaceConfigError(f"Cannot read workspace config file: {exc}") from exc

    return _parse_workspace_config(text, source_label=str(path))


# ################
# Implementation
# ################


def _parse_workspace_config(text: str, source_label: str = "<string>") -> WorkspaceConfig:
    """Parse workspace config YAML text into a WorkspaceConfig.

    Args:
        text: Raw YAML content.
        source_label: Human-readable label used in error messages (e.g. the file path).

    Returns:
        A WorkspaceConfig instance.

    Raises:
        WorkspaceConfigError: If the YAML is invalid or required fields are missing.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise WorkspaceConfigError(f"Invalid YAML in {source_label}: {exc}") from exc

    if not isinstance(data, dict):
        raise WorkspaceConfigError(f"{source_label}: workspace config must be a YAML mapping")

    build_directory = _require_string(data, "build-directory", source_label)

    source_imports: list[SourceImport] = []
    if "source-imports" in data:
        raw_imports = data["source-imports"]
        if not isinstance(raw_imports, list):
            raise WorkspaceConfigError(f"{source_label}: 'source-imports' must be a list")
        for index, entry in enumerate(raw_imports):
            source_imports.append(_parse_source_import(entry, index, source_label))

    return WorkspaceConfig(build_directory=build_directory, source_imports=source_imports)


def _require_string(mapping: dict[str, object], key: str, source_label: str) -> str:
    """Extract a required string field from a mapping, raising WorkspaceConfigError if missing."""
    if key not in mapping:
        raise WorkspaceConfigError(f"{source_label}: missing required field '{key}'")
    value = mapping[key]
    if not isinstance(value, str):
        raise WorkspaceConfigError(f"{source_label}: '{key}' must be a string")
    return value


def _parse_source_import(entry: object, index: int, source_label: str) -> SourceImport:
    """Parse a single source import entry from the YAML list."""
    location = f"{source_label}: source-imports[{index}]"

    if not isinstance(entry, dict):
        raise WorkspaceConfigError(f"{location} must be a YAML mapping")

    name = _require_string(entry, "name", location)

    has_local = "local-path" in entry
    has_git = "git-repository" in entry

    if has_local and has_git:
        raise WorkspaceConfigError(
            f"{location} '{name}': must specify either 'local-path' or 'git-repository', not both"
        )

    if not has_local and not has_git:
        raise WorkspaceConfigError(
            f"{location} '{name}': must specify either 'local-path' or 'git-repository'"
        )

    if has_local:
        local_path = _require_string(entry, "local-path", location)
        return LocalPathImport(name=name, local_path=local_path)

    git_repository = _require_string(entry, "git-repository", location)
    revision = _require_string(entry, "revision", location)
    return GitPathImport(name=name, git_repository=git_repository, revision=revision)
