# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Entity resolution for ArchML views.

Resolves ``::``-delimited entity paths (e.g. ``SystemA::ComponentB::Sub``)
to the corresponding :class:`~archml.model.entities.Component` or
:class:`~archml.model.entities.System` in a compiled model.
"""

from __future__ import annotations

from archml.model.entities import ArchFile, Component, System

# ###############
# Public Interface
# ###############


class EntityNotFoundError(Exception):
    """Raised when an entity path cannot be resolved in the model."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def resolve_entity(
    arch_files: dict[str, ArchFile],
    path: str,
) -> Component | System:
    """Resolve a ``::``-delimited entity path to a model entity.

    The first path segment identifies a top-level system or component (by
    name) across all provided *arch_files*.  Subsequent segments navigate
    into nested systems or components of the previously found entity.

    Examples::

        resolve_entity(files, "SystemA")
        resolve_entity(files, "SystemA::Worker")
        resolve_entity(files, "SystemA::SubSystem::ComponentX")

    Args:
        arch_files: Mapping from canonical file key to compiled
            :class:`~archml.model.entities.ArchFile`.
        path: ``::``-delimited path string identifying the target entity.

    Returns:
        The resolved :class:`~archml.model.entities.Component` or
        :class:`~archml.model.entities.System`.

    Raises:
        EntityNotFoundError: If any segment along the path cannot be found.
    """
    segments = [s.strip() for s in path.split("::")]
    if not segments or not any(segments):
        raise EntityNotFoundError(f"Invalid entity path: '{path}'")

    first = segments[0]
    entity: Component | System | None = _find_top_level(arch_files, first)
    if entity is None:
        raise EntityNotFoundError(
            f"Top-level entity '{first}' not found in any architecture file"
        )

    for segment in segments[1:]:
        entity = _find_child(entity, segment)
        if entity is None:
            raise EntityNotFoundError(
                f"Entity '{segment}' not found in path '{path}'"
            )

    return entity


# ################
# Implementation
# ################


def _find_top_level(
    arch_files: dict[str, ArchFile],
    name: str,
) -> Component | System | None:
    """Search all arch files for a top-level component or system by name."""
    for arch_file in arch_files.values():
        for system in arch_file.systems:
            if system.name == name:
                return system
        for component in arch_file.components:
            if component.name == name:
                return component
    return None


def _find_child(
    entity: Component | System,
    name: str,
) -> Component | System | None:
    """Search the direct children of *entity* for a member named *name*."""
    for comp in entity.components:
        if comp.name == name:
            return comp
    if isinstance(entity, System):
        for sub in entity.systems:
            if sub.name == name:
                return sub
    return None
