# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""JSON viewer payload serializer for the static ArchML HTML viewer.

This module converts the compiled architecture model into a self-contained
JSON document that can be embedded in a static HTML page and consumed by
the JavaScript viewer.

The payload contains two parts:

- **files** — the full compiled model serialized via Pydantic, keyed by the
  same canonical file keys used by the compiler.  The JS viewer uses this to
  reconstruct any topology on demand without network requests.
- **entities** — a pre-computed flat index of every viewable entity (systems
  and components at any nesting level) with their qualified names and kinds.
  The viewer populates its entity-selector dropdown from this list.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from archml.model.entities import ArchFile, Component, System

# ###############
# Public Interface
# ###############


@dataclass
class EntityEntry:
    """Metadata for a single viewable entity in the selector index.

    Attributes:
        qualified_name: Full ``::``-delimited path (e.g. ``"OrderSys::Cart"``).
        kind: One of ``"system"``, ``"component"``, ``"external_system"``, or
            ``"external_component"``.
        file_key: Canonical compiler key of the :class:`~archml.model.entities.ArchFile`
            that owns this entity.
    """

    qualified_name: str
    kind: str
    file_key: str


def build_viewer_payload(compiled: dict[str, ArchFile]) -> str:
    """Serialise a compiled workspace into the static viewer JSON payload.

    The returned string is valid JSON and is intended to be embedded verbatim
    inside a ``<script id="archml-data" type="application/json">`` element.

    Args:
        compiled: Mapping from canonical file key to compiled
            :class:`~archml.model.entities.ArchFile`, as returned by
            :func:`~archml.compiler.build.compile_files`.

    Returns:
        A compact JSON string containing the full model and entity index.
    """
    files_data = {key: arch_file.model_dump(mode="json") for key, arch_file in compiled.items()}
    entities = _collect_entities(compiled)
    payload: dict[str, object] = {
        "version": "1",
        "files": files_data,
        "entities": [
            {
                "qualified_name": e.qualified_name,
                "kind": e.kind,
                "file_key": e.file_key,
            }
            for e in entities
        ],
    }
    return json.dumps(payload, separators=(",", ":"))


# ################
# Implementation
# ################


def _collect_entities(compiled: dict[str, ArchFile]) -> list[EntityEntry]:
    """Walk all arch files and collect every viewable entity into a flat list."""
    entries: list[EntityEntry] = []
    for file_key, arch_file in compiled.items():
        for system in arch_file.systems:
            _collect_from_system(system, entries, file_key)
        for component in arch_file.components:
            _collect_from_component(component, entries, file_key)
    return entries


def _collect_from_system(system: System, entries: list[EntityEntry], file_key: str) -> None:
    """Append *system* and all its nested systems and components to *entries*."""
    kind = "external_system" if system.is_external else "system"
    entries.append(
        EntityEntry(
            qualified_name=system.qualified_name or system.name,
            kind=kind,
            file_key=file_key,
        )
    )
    for sub in system.systems:
        _collect_from_system(sub, entries, file_key)
    for comp in system.components:
        _collect_from_component(comp, entries, file_key)


def _collect_from_component(component: Component, entries: list[EntityEntry], file_key: str) -> None:
    """Append *component* and all its nested components to *entries*."""
    kind = "external_component" if component.is_external else "component"
    entries.append(
        EntityEntry(
            qualified_name=component.qualified_name or component.name,
            kind=kind,
            file_key=file_key,
        )
    )
    for sub in component.components:
        _collect_from_component(sub, entries, file_key)
