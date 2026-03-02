# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Diagram generation for ArchML architecture views.

Builds a diagram representation from a resolved model entity and renders it
to an image file using the ``diagrams`` library (which delegates layout to
Graphviz).

The diagram shows:
- The target entity as the outer container / title.
- All direct child components and systems as inner boxes inside a Cluster.
- The target entity's ``requires`` interfaces as incoming terminal nodes
  (left side, arrows pointing into the entity).
- The target entity's ``provides`` interfaces as outgoing terminal nodes
  (right side, arrows pointing out of the entity).
- Connections between child entities as labelled directed edges.
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
    """Render *data* to an image file at *output_path* using the ``diagrams`` library.

    Custom styled nodes are used for the entity, its children, and its interface
    terminals. Graphviz (via the ``diagrams`` library) handles layout automatically.

    For leaf entities (no children) a single entity node is placed between the
    terminal nodes. For entities with children a ``Cluster`` groups the children
    visually; requires terminals connect to the natural entry children and provides
    terminals connect from the natural exit children.

    The output format is determined by the file extension of *output_path*
    (e.g. ``.svg``, ``.png``).

    Args:
        data: The diagram description to render.
        output_path: Destination file path for the rendered image.

    Raises:
        ImportError: If the ``diagrams`` package is not installed.
    """
    try:
        import diagrams as _diagrams
        from diagrams import Cluster, Edge, Node
    except ImportError as exc:
        raise ImportError("'diagrams' is not installed. Run 'pip install diagrams' to enable visualization.") from exc

    # Custom node classes are defined locally to keep the diagrams import lazy
    # (it is an optional dependency that requires Graphviz to be installed).

    class _TerminalNode(Node):  # type: ignore[misc]
        """Styled box for an interface terminal (requires or provides)."""

        _icon_dir = None
        _icon = None
        _height = 1.2
        _attr = {
            "shape": "box",
            "style": "rounded,filled",
            "fillcolor": "#fff8e1",
            "color": "#aa8833",
            "penwidth": "1.5",
        }

    class _EntityNode(Node):  # type: ignore[misc]
        """Styled box for a leaf entity (component or system with no children)."""

        _icon_dir = None
        _icon = None
        _height = 1.5
        _attr = {
            "shape": "box",
            "style": "rounded,filled",
            "fillcolor": "#ddeeff",
            "color": "#4466aa",
            "penwidth": "2",
        }

    class _ChildNode(Node):  # type: ignore[misc]
        """Styled box for a child component or system inside an entity cluster."""

        _icon_dir = None
        _icon = None
        _height = 1.2
        _attr = {
            "shape": "box",
            "style": "rounded,filled",
            "fillcolor": "#e8f4e8",
            "color": "#448844",
            "penwidth": "1.5",
        }

    output_stem = str(output_path.parent / output_path.stem)
    output_format = output_path.suffix.lstrip(".") or "svg"

    with _diagrams.Diagram(data.title, filename=output_stem, outformat=output_format, show=False, direction="LR"):
        # --- Requires terminals (rendered left by Graphviz) ---
        req_nodes = {t.name: _TerminalNode(t.name) for t in data.terminals if t.direction == "in"}

        # --- Entity representation ---
        if data.children:
            # A Cluster groups children inside a visible border labelled with
            # the entity name; children are instantiated inside the context so
            # Graphviz assigns them to the subgraph automatically.
            with Cluster(data.title):
                child_nodes = {child.name: _ChildNode(child.name) for child in data.children}

            # Internal connections between children (drawn after the Cluster so
            # that cross-cluster edges are handled correctly by Graphviz).
            for conn in data.connections:
                if conn.source in child_nodes and conn.target in child_nodes:
                    child_nodes[conn.source] >> Edge(label=conn.label) >> child_nodes[conn.target]  # type: ignore[operator]

            # Children with no incoming internal connection are natural entry
            # points for requires terminals; those with no outgoing connection
            # are natural exit points for provides terminals.
            conn_targets = {c.target for c in data.connections if c.target in child_nodes}
            conn_sources = {c.source for c in data.connections if c.source in child_nodes}
            entry_nodes = [child_nodes[c.name] for c in data.children if c.name not in conn_targets]
            exit_nodes = [child_nodes[c.name] for c in data.children if c.name not in conn_sources]
            if not entry_nodes:
                entry_nodes = list(child_nodes.values())
            if not exit_nodes:
                exit_nodes = list(child_nodes.values())
        else:
            # Leaf entity: a single styled node represents the whole entity.
            entity_node = _EntityNode(data.title)
            entry_nodes = [entity_node]
            exit_nodes = [entity_node]

        # --- Provides terminals (rendered right by Graphviz) ---
        prov_nodes = {t.name: _TerminalNode(t.name) for t in data.terminals if t.direction == "out"}

        # --- Terminal ↔ entity edges ---
        for req_node in req_nodes.values():
            for entry in entry_nodes:
                req_node >> Edge() >> entry  # type: ignore[operator]

        for prov_node in prov_nodes.values():
            for exit_node in exit_nodes:
                exit_node >> Edge() >> prov_node  # type: ignore[operator]


# ################
# Implementation
# ################


def _iref_label(ref: InterfaceRef) -> str:
    """Return a display label for an interface reference."""
    return f"{ref.name}@{ref.version}" if ref.version else ref.name
