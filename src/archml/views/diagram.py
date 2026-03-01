# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Diagram generation for ArchML architecture views.

Builds a diagram representation from a resolved model entity and renders it
to an image file using the ``diagrams`` library.

The diagram shows:
- The target entity as the outer container / title.
- All direct child components and systems as inner boxes.
- The target entity's ``requires`` interfaces as incoming terminal elements.
- The target entity's ``provides`` interfaces as outgoing terminal elements.
- Connections between child entities as labelled arrows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from archml.model.entities import Component, InterfaceRef, System

# ###############
# Public Interface
# ###############


@dataclass
class ChildBox:
    """Represents a direct child component or system in the diagram.

    Attributes:
        name: Short name of the child entity.
        description: Optional human-readable description.
        kind: ``"component"`` or ``"system"``.
    """

    name: str
    description: str | None
    kind: str  # "component" | "system"


@dataclass
class InterfaceTerminal:
    """Represents an external interface terminal (incoming or outgoing).

    Attributes:
        name: Interface name (optionally with version suffix ``@vN``).
        direction: ``"in"`` for ``requires``, ``"out"`` for ``provides``.
        description: Optional description of the interface.
    """

    name: str
    direction: str  # "in" | "out"
    description: str | None = None


@dataclass
class ConnectionData:
    """Represents a directed connection between two child entities.

    Attributes:
        source: Name of the source child entity.
        target: Name of the target child entity.
        label: Interface name used by the connection.
    """

    source: str
    target: str
    label: str


@dataclass
class DiagramData:
    """Full description of a diagram to be rendered.

    Attributes:
        title: Name of the target entity (used as the diagram title/box).
        description: Optional human-readable description of the entity.
        children: Direct child components and systems.
        terminals: External interface terminals (in/out).
        connections: Directed data-flow connections between children.
    """

    title: str
    description: str | None
    children: list[ChildBox] = field(default_factory=list)
    terminals: list[InterfaceTerminal] = field(default_factory=list)
    connections: list[ConnectionData] = field(default_factory=list)


def build_diagram_data(entity: Component | System) -> DiagramData:
    """Build a :class:`DiagramData` description from a model entity.

    Collects direct children, external interface terminals, and connections
    from *entity* without navigating deeper into the hierarchy.

    Args:
        entity: The resolved component or system to visualize.

    Returns:
        A :class:`DiagramData` instance describing the diagram.
    """
    children: list[ChildBox] = [
        ChildBox(name=comp.name, description=comp.description, kind="component") for comp in entity.components
    ]
    if isinstance(entity, System):
        children += [ChildBox(name=sys.name, description=sys.description, kind="system") for sys in entity.systems]

    terminals: list[InterfaceTerminal] = [
        InterfaceTerminal(
            name=_iref_label(ref),
            direction="in",
        )
        for ref in entity.requires
    ] + [
        InterfaceTerminal(
            name=_iref_label(ref),
            direction="out",
        )
        for ref in entity.provides
    ]

    connections: list[ConnectionData] = [
        ConnectionData(
            source=conn.source.entity,
            target=conn.target.entity,
            label=_iref_label(conn.interface),
        )
        for conn in entity.connections
    ]

    return DiagramData(
        title=entity.name,
        description=entity.description,
        children=children,
        terminals=terminals,
        connections=connections,
    )


def render_diagram(data: DiagramData, output_path: Path) -> None:
    """Render *data* to an image file at *output_path* using ``diagrams``.

    The output format is determined by the file extension of *output_path*
    (e.g. ``.png``, ``.svg``).

    Args:
        data: The diagram description to render.
        output_path: Destination file path for the rendered image.

    Raises:
        ImportError: If the ``diagrams`` package is not installed.
    """
    try:
        import diagrams as _diagrams
        from diagrams import Edge
        from diagrams.c4 import Container, Person
    except ImportError as exc:
        raise ImportError("'diagrams' is not installed. Run 'pip install diagrams' to enable visualization.") from exc

    output_stem = str(output_path.parent / output_path.stem)
    output_format = output_path.suffix.lstrip(".") or "svg"

    with _diagrams.Diagram(data.title, filename=output_stem, outformat=output_format, show=False):
        for terminal in data.terminals:
            if terminal.direction == "in":
                Person(terminal.name)

        child_nodes: dict[str, object] = {}
        for child in data.children:
            child_nodes[child.name] = Container(child.name, technology=child.kind, description=child.description or "")

        for terminal in data.terminals:
            if terminal.direction == "out":
                Person(terminal.name)

        for conn in data.connections:
            if conn.source in child_nodes and conn.target in child_nodes:
                child_nodes[conn.source] >> Edge(label=conn.label) >> child_nodes[conn.target]  # type: ignore[operator]


# ################
# Implementation
# ################


def _iref_label(ref: InterfaceRef) -> str:
    """Return a display label for an interface reference."""
    return f"{ref.name}@{ref.version}" if ref.version else ref.name
