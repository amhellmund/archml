# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Abstract visualization topology model for ArchML diagrams.

This module defines an intermediate representation of a diagram's topology
that is independent of both the architecture domain model and any rendering
backend.  The same topology drives SVG export, interactive Dash views, and
any future renderer.

The topology model captures:

- **VizNode** — an opaque box (leaf component, system, external actor, or
  interface terminal).
- **VizBoundary** — a labelled visual container grouping child nodes and/or
  nested sub-boundaries.  Corresponds to a component or system whose internal
  structure is expanded at this zoom level.
- **VizPort** — a named interface connection point on a node or boundary.
  Every ``requires``/``provides`` declaration in the architecture model
  becomes a port.  Ports are the endpoints of edges.
- **VizEdge** — a directed connection between two ports, derived from an
  ArchML ``connect`` statement.
- **VizDiagram** — the assembled complete topology: root boundary, peripheral
  nodes (terminals + externals), and all edges.

Geometry (positions, sizes, edge waypoints) is deliberately absent.  A
separate layout step computes geometry and attaches it to a layout model.
This decoupling lets a single topology feed both headless layout algorithms
and interactive, event-driven frontends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from archml.model.entities import Component, InterfaceRef, System, UserDef

# ###############
# Public Interface
# ###############

NodeKind = Literal["component", "system", "user", "external_component", "external_system", "external_user", "terminal"]
"""Semantic classification of a :class:`VizNode`."""

BoundaryKind = Literal["component", "system"]
"""Semantic classification of a :class:`VizBoundary`."""


@dataclass
class VizPort:
    """A named interface connection point on a :class:`VizNode` or :class:`VizBoundary`.

    Ports are the typed endpoints of :class:`VizEdge` connections.  Each
    ``requires`` or ``provides`` declaration on an architecture entity produces
    one port.

    Attributes:
        id: Diagram-unique stable identifier used by :class:`VizEdge` and
            renderers (e.g. ``"ECommerce__OrderService.req.PaymentRequest"``).
        node_id: ID of the owning :class:`VizNode` or :class:`VizBoundary`.
        interface_name: Base interface name without the version suffix.
        interface_version: Version string (e.g. ``"v2"``), or ``None`` for
            unversioned interfaces.
        direction: ``"requires"`` for input ports; ``"provides"`` for output
            ports.
        description: Optional human-readable description of the interface.
    """

    id: str
    node_id: str
    interface_name: str
    interface_version: str | None
    direction: Literal["requires", "provides"]
    description: str | None = None


@dataclass
class VizNode:
    """A renderable box representing a leaf entity or interface terminal.

    A *leaf entity* is a component, system, or external actor whose internal
    structure is not expanded in this diagram — it appears as an opaque box.
    A *terminal* represents one of the focus entity's own ``requires`` or
    ``provides`` interfaces, anchored at the diagram boundary.

    Attributes:
        id: Diagram-unique stable identifier (e.g. ``"ECommerce__OrderService"``
            or ``"terminal.req.OrderRequest"``).
        label: Short display name — typically the entity mnemonic.
        title: Human-readable title if distinct from *label*; ``None``
            otherwise.
        kind: Semantic classification that determines default visual styling.
        entity_path: ``::``-delimited qualified path for navigation and
            deep-linking (e.g. ``"ECommerce::OrderService"``).  Empty string
            for terminal nodes.
        description: Tooltip / hover text; ``None`` if absent.
        tags: Arbitrary labels inherited from the ArchML model, used for
            filtering and conditional styling.
        ports: Interface ports belonging to this node (requires and provides).
    """

    id: str
    label: str
    title: str | None
    kind: NodeKind
    entity_path: str
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    ports: list[VizPort] = field(default_factory=list)


@dataclass
class VizBoundary:
    """A labelled visual container grouping child nodes and/or sub-boundaries.

    Boundaries represent container entities — components or systems whose
    internal structure is rendered at this zoom level.  They are drawn with a
    visible bounding box and a title label.

    Attributes:
        id: Diagram-unique stable identifier.
        label: Short display name.
        title: Human-readable title if distinct from *label*; ``None``
            otherwise.
        kind: ``"component"`` or ``"system"``.
        entity_path: Qualified path for navigation and deep-linking.
        description: Tooltip / hover text; ``None`` if absent.
        tags: Arbitrary labels from the ArchML model.
        ports: The boundary entity's own interface ports (its ``requires`` and
            ``provides`` declarations).
        children: Direct visual children — a mix of leaf :class:`VizNode`
            instances and nested :class:`VizBoundary` instances for recursively
            expanded sub-entities.
    """

    id: str
    label: str
    title: str | None
    kind: BoundaryKind
    entity_path: str
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    ports: list[VizPort] = field(default_factory=list)
    children: list[VizNode | VizBoundary] = field(default_factory=list)


@dataclass
class VizEdge:
    """A directed connection between two ports in the diagram.

    Edges correspond to ArchML ``connect`` statements.  The direction follows
    the ArchML convention: the *source* is the requiring side (initiator), the
    *target* is the providing side (responder), and the arrow represents the
    request direction.

    Attributes:
        id: Diagram-unique stable identifier derived from the port IDs
            (e.g. ``"edge.A.req.IFace--B.prov.IFace"``).
        source_port_id: ID of the source :class:`VizPort` (a ``requires``
            port).
        target_port_id: ID of the target :class:`VizPort` (a ``provides``
            port).
        label: Human-readable label shown on the edge
            (``"InterfaceName"`` or ``"InterfaceName@vN"``).
        interface_name: Base interface name without version suffix.
        interface_version: Version string, or ``None``.
        protocol: Optional transport protocol annotation (e.g. ``"gRPC"``).
        is_async: Whether the connection is asynchronous.
        description: Optional human-readable description of the connection.
    """

    id: str
    source_port_id: str
    target_port_id: str
    label: str
    interface_name: str
    interface_version: str | None = None
    protocol: str | None = None
    is_async: bool = False
    description: str | None = None


@dataclass
class VizDiagram:
    """Complete topology description of a visualization diagram.

    A :class:`VizDiagram` is built from a single *focus entity* (a
    :class:`~archml.model.entities.Component` or
    :class:`~archml.model.entities.System`).

    - The focus entity becomes the :attr:`root` :class:`VizBoundary`.
    - Its direct children are placed inside the root as :class:`VizNode`
      instances (opaque at this zoom level).
    - The focus entity's own ``requires``/``provides`` interfaces appear as
      terminal :class:`VizNode` instances in :attr:`peripheral_nodes`.
    - External actors that appear as connection endpoints but are not children
      of the focus entity also appear in :attr:`peripheral_nodes`.
    - All ArchML ``connect`` statements within the focus entity become
      :class:`VizEdge` entries in :attr:`edges`.

    Geometry (positions, sizes, edge routes) is not part of this model; it is
    computed by a separate layout step.

    Attributes:
        id: Stable diagram identifier derived from the focus entity path
            (e.g. ``"diagram.ECommerce"``).
        title: Display title for the diagram.
        description: Optional longer description of the focus entity.
        root: The focus entity rendered as a :class:`VizBoundary`.
        peripheral_nodes: Terminal and external :class:`VizNode` instances
            that appear outside the root boundary.
        edges: All directed connections visible in the diagram.
    """

    id: str
    title: str
    description: str | None
    root: VizBoundary
    peripheral_nodes: list[VizNode] = field(default_factory=list)
    edges: list[VizEdge] = field(default_factory=list)


def build_viz_diagram(
    entity: Component | System,
) -> VizDiagram:
    """Build a :class:`VizDiagram` topology from a model entity.

    The *entity* becomes the root :class:`VizBoundary`.  Its direct children
    are placed inside the boundary as opaque :class:`VizNode` instances.

    The entity's own ``requires``/``provides`` interfaces become *terminal*
    :class:`VizNode` instances in ``peripheral_nodes`` — one node per
    interface, positioned at the diagram boundary.

    For each channel declared on the entity, components that bind to it via a
    ``requires X via channel`` or ``provides X via channel`` declaration become
    the endpoints of a :class:`VizEdge`.  All providers and requirers of the
    same channel are cross-connected pairwise.

    Args:
        entity: The focus component or system to visualize.

    Returns:
        A :class:`VizDiagram` describing the full diagram topology.
    """
    entity_path = entity.qualified_name or entity.name
    root_id = _make_id(entity_path)

    # --- Child nodes (direct children rendered as opaque boxes) ---
    child_node_map: dict[str, VizNode] = {}
    for comp in entity.components:
        child_path = f"{entity_path}::{comp.name}"
        child_node_map[comp.name] = _make_child_node(comp, child_path)

    if isinstance(entity, System):
        for sys in entity.systems:
            child_path = f"{entity_path}::{sys.name}"
            child_node_map[sys.name] = _make_child_node(sys, child_path)
        for user in entity.users:
            child_path = f"{entity_path}::{user.name}"
            child_node_map[user.name] = _make_child_node(user, child_path)

    # --- Root boundary ---
    root_ports = _make_ports(root_id, entity)
    root = VizBoundary(
        id=root_id,
        label=entity.name,
        title=entity.title,
        kind="component" if isinstance(entity, Component) else "system",
        entity_path=entity_path,
        description=entity.description,
        tags=list(entity.tags),
        ports=root_ports,
        children=list(child_node_map.values()),
    )

    # --- Peripheral nodes (terminal interface anchors at the diagram boundary) ---
    peripheral_nodes: list[VizNode] = []
    for ref in entity.requires:
        peripheral_nodes.append(_make_terminal_node(ref, "requires"))
    for ref in entity.provides:
        peripheral_nodes.append(_make_terminal_node(ref, "provides"))

    # --- Sub-entity map for channel binding lookup ---
    all_sub_entity_map: dict[str, Component | System | UserDef] = {}
    for comp in entity.components:
        all_sub_entity_map[comp.name] = comp
    if isinstance(entity, System):
        for sys in entity.systems:
            all_sub_entity_map[sys.name] = sys
        for user in entity.users:
            all_sub_entity_map[user.name] = user

    # --- Edges (derived from channel bindings) ---
    edges: list[VizEdge] = []
    for channel in entity.channels:
        providers: list[tuple[str, InterfaceRef]] = []
        requirers: list[tuple[str, InterfaceRef]] = []
        for sub_name, sub_entity in all_sub_entity_map.items():
            for ref in sub_entity.provides:
                if ref.via == channel.name:
                    providers.append((sub_name, ref))
            for ref in sub_entity.requires:
                if ref.via == channel.name:
                    requirers.append((sub_name, ref))

        for req_name, req_ref in requirers:
            for prov_name, prov_ref in providers:
                req_node = child_node_map.get(req_name)
                prov_node = child_node_map.get(prov_name)
                if req_node is None or prov_node is None:
                    continue

                src_port_id = _find_port_id(req_node, "requires", req_ref)
                tgt_port_id = _find_port_id(prov_node, "provides", prov_ref)

                if src_port_id is None:
                    p = _make_port(req_node.id, "requires", req_ref)
                    req_node.ports.append(p)
                    src_port_id = p.id

                if tgt_port_id is None:
                    p = _make_port(prov_node.id, "provides", prov_ref)
                    prov_node.ports.append(p)
                    tgt_port_id = p.id

                label = _iref_label(channel.interface)
                edges.append(
                    VizEdge(
                        id=f"edge.{src_port_id}--{tgt_port_id}",
                        source_port_id=src_port_id,
                        target_port_id=tgt_port_id,
                        label=label,
                        interface_name=channel.interface.name,
                        interface_version=channel.interface.version,
                        protocol=channel.protocol,
                        is_async=channel.is_async,
                        description=channel.description,
                    )
                )

    return VizDiagram(
        id=f"diagram.{root_id}",
        title=entity.title or entity.name,
        description=entity.description,
        root=root,
        peripheral_nodes=peripheral_nodes,
        edges=edges,
    )


def collect_all_ports(diagram: VizDiagram) -> dict[str, VizPort]:
    """Return a flat ``port_id → VizPort`` mapping for the entire diagram.

    Traverses the root boundary (including any nested sub-boundaries), all
    peripheral nodes, and the root boundary's own ports.

    Args:
        diagram: The diagram to collect ports from.

    Returns:
        Dictionary mapping each port's stable ID to the
        :class:`VizPort` instance.
    """
    result: dict[str, VizPort] = {}
    _collect_boundary_ports(diagram.root, result)
    for node in diagram.peripheral_nodes:
        for p in node.ports:
            result[p.id] = p
    return result


# ################
# Implementation
# ################


def _make_id(entity_path: str) -> str:
    """Convert a ``::``-delimited entity path to a DOM/URL-safe element ID."""
    return entity_path.replace("::", "__")


def _iref_label(ref: InterfaceRef) -> str:
    """Return a display label for an interface reference."""
    return f"{ref.name}@{ref.version}" if ref.version else ref.name


def _port_id(node_id: str, direction: Literal["requires", "provides"], ref: InterfaceRef) -> str:
    """Construct a stable port ID from its owner, direction, and interface."""
    dir_tag = "req" if direction == "requires" else "prov"
    suffix = f"{ref.name}@{ref.version}" if ref.version else ref.name
    return f"{node_id}.{dir_tag}.{suffix}"


def _make_port(
    node_id: str,
    direction: Literal["requires", "provides"],
    ref: InterfaceRef,
) -> VizPort:
    """Create a :class:`VizPort` for a single interface reference."""
    return VizPort(
        id=_port_id(node_id, direction, ref),
        node_id=node_id,
        interface_name=ref.name,
        interface_version=ref.version,
        direction=direction,
    )


def _make_ports(node_id: str, entity: Component | System | UserDef) -> list[VizPort]:
    """Create :class:`VizPort` instances for all requires and provides of *entity*."""
    ports: list[VizPort] = []
    for ref in entity.requires:
        ports.append(_make_port(node_id, "requires", ref))
    for ref in entity.provides:
        ports.append(_make_port(node_id, "provides", ref))
    return ports


def _make_child_node(entity: Component | System | UserDef, entity_path: str) -> VizNode:
    """Create a :class:`VizNode` for a direct child of the focus entity."""
    node_id = _make_id(entity_path)
    if isinstance(entity, Component):
        kind: NodeKind = "external_component" if entity.is_external else "component"
    elif isinstance(entity, System):
        kind = "external_system" if entity.is_external else "system"
    else:
        kind = "external_user" if entity.is_external else "user"
    return VizNode(
        id=node_id,
        label=entity.name,
        title=entity.title,
        kind=kind,
        entity_path=entity_path,
        description=entity.description,
        tags=list(entity.tags),
        ports=_make_ports(node_id, entity),
    )


def _make_terminal_node(
    ref: InterfaceRef,
    direction: Literal["requires", "provides"],
) -> VizNode:
    """Create a terminal :class:`VizNode` for the focus entity's own interface port.

    A terminal node anchors the focus entity's external interface boundary
    visually: ``requires`` terminals appear on the input side of the diagram,
    ``provides`` terminals on the output side.  Each terminal carries exactly
    one port mirroring the interface direction.
    """
    label = _iref_label(ref)
    dir_tag = "req" if direction == "requires" else "prov"
    node_id = f"terminal.{dir_tag}.{label}"
    port = VizPort(
        id=f"{node_id}.port",
        node_id=node_id,
        interface_name=ref.name,
        interface_version=ref.version,
        direction=direction,
    )
    return VizNode(
        id=node_id,
        label=label,
        title=None,
        kind="terminal",
        entity_path="",
        ports=[port],
    )


def _find_port_id(
    node: VizNode,
    direction: Literal["requires", "provides"],
    ref: InterfaceRef,
) -> str | None:
    """Return the port ID matching *direction* and *ref* on *node*, or ``None``."""
    for p in node.ports:
        if p.direction == direction and p.interface_name == ref.name and p.interface_version == ref.version:
            return p.id
    return None


def _collect_boundary_ports(boundary: VizBoundary, result: dict[str, VizPort]) -> None:
    """Recursively collect all ports from *boundary* and its children into *result*."""
    for p in boundary.ports:
        result[p.id] = p
    for child in boundary.children:
        if isinstance(child, VizBoundary):
            _collect_boundary_ports(child, result)
        else:
            for p in child.ports:
                result[p.id] = p
