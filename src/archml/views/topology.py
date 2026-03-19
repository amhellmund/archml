# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Abstract visualization topology model for ArchML diagrams.

This module defines an intermediate representation of a diagram's topology
that is independent of both the architecture domain model and any rendering
backend.  The same topology drives SVG export, interactive Dash views, and
any future renderer.

The topology model captures:

- **VizNode** — an opaque box (leaf component, system, external actor,
  interface terminal, or channel).
- **VizBoundary** — a labelled visual container grouping child nodes and/or
  nested sub-boundaries.  Corresponds to a component or system whose internal
  structure is expanded at this zoom level.
- **VizPort** — a named interface connection point on a node or boundary.
  Every ``requires``/``provides`` declaration in the architecture model
  becomes a port.  Ports are the endpoints of edges.
- **VizEdge** — a directed connection between two ports, derived from an
  ArchML ``connect`` statement.  Connects through a channel produce two
  edges: one leading into the channel and one leaving it.
- **VizDiagram** — the assembled complete topology: root boundary, peripheral
  nodes (terminals + externals), and all edges.

Geometry (positions, sizes, edge waypoints) is deliberately absent.  A
separate layout step computes geometry and attaches it to a layout model.
This decoupling lets a single topology feed both headless layout algorithms
and interactive, event-driven frontends.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from archml.model.entities import ArchFile, Component, ConnectDef, InterfaceRef, System, UserDef

# ###############
# Public Interface
# ###############

NodeKind = Literal[
    "component", "system", "user", "external_component", "external_system", "external_user", "terminal", "channel"
]
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
    A *channel* represents a named communication channel introduced by a
    ``connect`` statement.

    Attributes:
        id: Diagram-unique stable identifier (e.g. ``"ECommerce__OrderService"``
            or ``"terminal.req.OrderRequest"``).
        label: Short display name — typically the entity mnemonic.
        title: Human-readable title if distinct from *label*; ``None``
            otherwise.
        kind: Semantic classification that determines default visual styling.
        entity_path: ``::``-delimited qualified path for navigation and
            deep-linking (e.g. ``"ECommerce::OrderService"``).  Empty string
            for terminal and channel nodes.
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

    Edges correspond to ArchML ``connect`` statements.  For connects that
    route through a named channel, two edges are produced: one from the
    source port to the channel's input port, and one from the channel's
    output port to the destination port.

    For direct connects (no channel), a single edge is produced.

    Attributes:
        id: Diagram-unique stable identifier derived from the port IDs
            (e.g. ``"edge.A.req.IFace--B.prov.IFace"``).
        source_port_id: ID of the source :class:`VizPort`.
        target_port_id: ID of the target :class:`VizPort`.
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
    - Named channels referenced in ``connect`` statements appear as
      :class:`VizNode` instances with ``kind="channel"`` inside the root.
    - The focus entity's own ``requires``/``provides`` interfaces appear as
      terminal :class:`VizNode` instances in :attr:`peripheral_nodes`.
    - External actors that appear as connection endpoints but are not children
      of the focus entity also appear in :attr:`peripheral_nodes`.
    - All ArchML ``connect`` statements within the focus entity become
      :class:`VizEdge` entries in :attr:`edges`.  Connects through a channel
      produce two edges each (source→channel and channel→destination).

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
    Named channels referenced in the entity's ``connect`` statements also
    appear as child nodes with ``kind="channel"``.

    The entity's own ``requires``/``provides`` interfaces become *terminal*
    :class:`VizNode` instances in ``peripheral_nodes`` — one node per
    interface, positioned at the diagram boundary.

    Each ``connect`` statement on the entity produces :class:`VizEdge`
    instances.  A connect through a named channel produces two edges (one
    entering the channel, one leaving it); a direct connect produces one.
    One-sided connects where only the source or only the destination is
    specified produce a single edge to or from the channel node.
    Duplicate edges (same source and target ports) are deduplicated.

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

    # --- Sub-entity map for connect statement port lookup ---
    all_sub_entity_map: dict[str, Component | System | UserDef] = {}
    for comp in entity.components:
        all_sub_entity_map[comp.name] = comp
    if isinstance(entity, System):
        for sys in entity.systems:
            all_sub_entity_map[sys.name] = sys
        for user in entity.users:
            all_sub_entity_map[user.name] = user

    # --- Channel nodes (from connect statements in this scope) ---
    channel_node_map = _collect_channel_nodes(entity.connects, root_id, all_sub_entity_map)

    # --- Root boundary ---
    root_ports = _make_ports(root_id, entity)
    all_children: list[VizNode | VizBoundary] = [*child_node_map.values(), *channel_node_map.values()]
    root = VizBoundary(
        id=root_id,
        label=entity.name,
        title=entity.title,
        kind="component" if isinstance(entity, Component) else "system",
        entity_path=entity_path,
        description=entity.description,
        tags=list(entity.tags),
        ports=root_ports,
        children=all_children,
    )

    # --- Peripheral nodes (terminal interface anchors at the diagram boundary) ---
    peripheral_nodes: list[VizNode] = []
    for ref in entity.requires:
        peripheral_nodes.append(_make_terminal_node(ref, "requires"))
    for ref in entity.provides:
        peripheral_nodes.append(_make_terminal_node(ref, "provides"))

    # --- Edges (derived from connect statements, deduplicated by port pair) ---
    edges: list[VizEdge] = []
    seen_port_pairs: set[tuple[str, str]] = set()
    for conn in entity.connects:
        for edge in _build_edges_from_connect(conn, child_node_map, all_sub_entity_map, channel_node_map):
            key = (edge.source_port_id, edge.target_port_id)
            if key not in seen_port_pairs:
                seen_port_pairs.add(key)
                edges.append(edge)

    # --- Terminal boundary edges ---
    # Connect each terminal node to the root boundary's matching port so that
    # arrows are drawn even when the focus entity has no internal connect statements
    # (e.g. a leaf component whose connections are defined at the parent level).
    for ref in entity.requires:
        terminal_id = f"terminal.req.{_iref_label(ref)}"
        terminal_port_id = f"{terminal_id}.port"
        root_port_id = _port_id(root_id, "requires", ref)
        key = (terminal_port_id, root_port_id)
        if key not in seen_port_pairs:
            seen_port_pairs.add(key)
            edges.append(
                VizEdge(
                    id=f"edge.{terminal_port_id}--{root_port_id}",
                    source_port_id=terminal_port_id,
                    target_port_id=root_port_id,
                    label=_iref_label(ref),
                    interface_name=ref.name,
                    interface_version=ref.version,
                )
            )
    for ref in entity.provides:
        terminal_id = f"terminal.prov.{_iref_label(ref)}"
        terminal_port_id = f"{terminal_id}.port"
        root_port_id = _port_id(root_id, "provides", ref)
        key = (root_port_id, terminal_port_id)
        if key not in seen_port_pairs:
            seen_port_pairs.add(key)
            edges.append(
                VizEdge(
                    id=f"edge.{root_port_id}--{terminal_port_id}",
                    source_port_id=root_port_id,
                    target_port_id=terminal_port_id,
                    label=_iref_label(ref),
                    interface_name=ref.name,
                    interface_version=ref.version,
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


def build_viz_diagram_all(arch_files: dict[str, ArchFile]) -> VizDiagram:
    """Build a :class:`VizDiagram` showing all top-level entities across *arch_files*.

    Creates a synthetic root boundary labelled ``"Architecture"`` whose
    children are every top-level :class:`~archml.model.entities.Component`,
    :class:`~archml.model.entities.System`, and
    :class:`~archml.model.entities.UserDef` found in any of the given files.
    Top-level ``connect`` statements from all files provide the edges and
    channel nodes.

    Non-external components and systems that have inner children (components,
    sub-systems, or users) are rendered as expanded :class:`VizBoundary`
    instances so their internal structure is visible.  Expansion is recursive:
    an expanded entity's children that themselves have sub-entities are also
    expanded.  External entities and leaf entities are opaque :class:`VizNode`
    instances.

    When a ``connect`` targets a port on an expanded entity, resolution follows
    the entity's ``expose`` chain all the way to the leaf component that owns
    the port, regardless of nesting depth.

    Use this to visualise the complete architecture in one diagram without
    selecting a specific entity.

    Args:
        arch_files: Mapping from canonical file key to compiled
            :class:`~archml.model.entities.ArchFile`, as returned by
            :func:`~archml.compiler.build.compile_files`.

    Returns:
        A :class:`VizDiagram` describing the full architecture topology.
    """
    root_id = "all"

    # expose_maps: entity_name → dict mapping exposed-port-name → (leaf_node, leaf_entity, leaf_port)
    # Used to resolve ports on expanded entities through the full expose chain.
    _ExposeMap = dict[str, tuple[VizNode, "Component | System | UserDef", str]]

    opaque_node_map: dict[str, VizNode] = {}
    all_sub_entity_map: dict[str, Component | System | UserDef] = {}
    expanded_boundary_map: dict[str, VizBoundary] = {}
    expanded_expose_maps: dict[str, _ExposeMap] = {}
    all_inner_edges: list[VizEdge] = []
    all_connects: list[ConnectDef] = []

    for arch_file in arch_files.values():
        for comp in arch_file.components:
            entity_path = comp.qualified_name or comp.name
            all_sub_entity_map[comp.name] = comp
            if _should_expand(comp):
                bnd, inner_edges, expose_map = _build_recursive_boundary(comp, entity_path)
                expanded_boundary_map[comp.name] = bnd
                expanded_expose_maps[comp.name] = expose_map
                all_inner_edges.extend(inner_edges)
            else:
                opaque_node_map[comp.name] = _make_child_node(comp, entity_path)
        for sys in arch_file.systems:
            entity_path = sys.qualified_name or sys.name
            all_sub_entity_map[sys.name] = sys
            if _should_expand(sys):
                bnd, inner_edges, expose_map = _build_recursive_boundary(sys, entity_path)
                expanded_boundary_map[sys.name] = bnd
                expanded_expose_maps[sys.name] = expose_map
                all_inner_edges.extend(inner_edges)
            else:
                opaque_node_map[sys.name] = _make_child_node(sys, entity_path)
        for user in arch_file.users:
            entity_path = user.qualified_name or user.name
            all_sub_entity_map[user.name] = user
            opaque_node_map[user.name] = _make_child_node(user, entity_path)
        all_connects.extend(arch_file.connects)

    channel_node_map = _collect_channel_nodes(all_connects, root_id, all_sub_entity_map)

    all_children: list[VizNode | VizBoundary] = [
        *opaque_node_map.values(),
        *expanded_boundary_map.values(),
        *channel_node_map.values(),
    ]
    root = VizBoundary(
        id=root_id,
        label="Architecture",
        title=None,
        kind="system",
        entity_path="",
        children=all_children,
    )

    edges: list[VizEdge] = []
    seen_port_pairs: set[tuple[str, str]] = set()

    # Inner edges collected during recursive boundary building.
    for edge in all_inner_edges:
        key = (edge.source_port_id, edge.target_port_id)
        if key not in seen_port_pairs:
            seen_port_pairs.add(key)
            edges.append(edge)

    # Top-level edges — resolve exposed ports through the full expose chain.
    for conn in all_connects:
        for edge in _build_edges_from_connect_expanded(
            conn,
            opaque_node_map,
            all_sub_entity_map,
            channel_node_map,
            expanded_expose_maps,
        ):
            key = (edge.source_port_id, edge.target_port_id)
            if key not in seen_port_pairs:
                seen_port_pairs.add(key)
                edges.append(edge)

    return VizDiagram(
        id="diagram.all",
        title="Architecture",
        description=None,
        root=root,
        edges=edges,
    )


def collect_all_ports(diagram: VizDiagram) -> dict[str, VizPort]:
    """Return a flat ``port_id → VizPort`` mapping for the entire diagram.

    Traverses the root boundary (including any nested sub-boundaries and
    channel nodes), all peripheral nodes, and the root boundary's own ports.

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
    visually: ``requires`` terminals appear on the input (left) side of the
    diagram, ``provides`` terminals on the output (right) side.

    The terminal's port direction is the **opposite** of the interface direction
    so that the port anchor faces the boundary (i.e. the connection point is
    on the side closest to the root boundary):

    - A ``requires`` terminal sits to the *left* and acts as an external
      provider → its port is ``"provides"`` (anchored to the right edge).
    - A ``provides`` terminal sits to the *right* and acts as an external
      consumer → its port is ``"requires"`` (anchored to the left edge).
    """
    label = _iref_label(ref)
    dir_tag = "req" if direction == "requires" else "prov"
    node_id = f"terminal.{dir_tag}.{label}"
    port_direction: Literal["requires", "provides"] = "provides" if direction == "requires" else "requires"
    port = VizPort(
        id=f"{node_id}.port",
        node_id=node_id,
        interface_name=ref.name,
        interface_version=ref.version,
        direction=port_direction,
    )
    return VizNode(
        id=node_id,
        label=label,
        title=None,
        kind="terminal",
        entity_path="",
        ports=[port],
    )


def _collect_channel_nodes(
    connects: list[ConnectDef],
    root_id: str,
    sub_entity_map: dict[str, Component | System | UserDef],
) -> dict[str, VizNode]:
    """Build :class:`VizNode` instances for all named channels in *connects*.

    Each unique channel name in the connect statements becomes one channel
    node placed inside the root boundary.  The channel's interface label is
    inferred from the first resolvable src or dst port that mentions it.

    Args:
        connects: The ``connect`` statements of the focus entity.
        root_id: ID prefix for channel node IDs (the root boundary ID).
        sub_entity_map: Map of child entity name to entity model, used to
            resolve port interface names.

    Returns:
        Map of channel name to the :class:`VizNode` representing it.
    """
    # First pass: collect channel names and try to resolve interface labels.
    channel_interfaces: dict[str, str | None] = {}
    for conn in connects:
        if conn.channel is None:
            continue
        ch = conn.channel
        if ch not in channel_interfaces:
            channel_interfaces[ch] = None
        if channel_interfaces[ch] is not None:
            continue
        # Try src port first.
        if conn.src_entity and conn.src_port:
            sub = sub_entity_map.get(conn.src_entity)
            if sub:
                result = _find_ref_by_port_name(sub, conn.src_port)
                if result:
                    _, ref = result
                    channel_interfaces[ch] = _iref_label(ref)
        # Fall back to dst port.
        if channel_interfaces[ch] is None and conn.dst_entity and conn.dst_port:
            sub = sub_entity_map.get(conn.dst_entity)
            if sub:
                result = _find_ref_by_port_name(sub, conn.dst_port)
                if result:
                    _, ref = result
                    channel_interfaces[ch] = _iref_label(ref)

    # Second pass: create VizNode for each channel.
    channel_nodes: dict[str, VizNode] = {}
    for ch_name, iface_label in channel_interfaces.items():
        ch_id = f"{root_id}.channel.{ch_name}"
        display_iface = iface_label or ch_name
        ports = [
            VizPort(
                id=f"{ch_id}.in",
                node_id=ch_id,
                interface_name=display_iface,
                interface_version=None,
                direction="requires",
            ),
            VizPort(
                id=f"{ch_id}.out",
                node_id=ch_id,
                interface_name=display_iface,
                interface_version=None,
                direction="provides",
            ),
        ]
        channel_nodes[ch_name] = VizNode(
            id=ch_id,
            label=ch_name,
            title=iface_label,
            kind="channel",
            entity_path="",
            ports=ports,
        )

    return channel_nodes


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


def _find_ref_by_port_name(
    entity: Component | System | UserDef,
    port_name: str,
) -> tuple[Literal["requires", "provides"], InterfaceRef] | None:
    """Find the direction and interface ref for a named port on *entity*.

    The effective port name is ``ref.port_name`` when explicitly aliased with
    ``as``, otherwise the interface name ``ref.name``.

    Returns a ``(direction, ref)`` tuple, or ``None`` if not found.
    """
    for ref in entity.requires:
        effective = ref.port_name if ref.port_name else ref.name
        if effective == port_name:
            return ("requires", ref)
    for ref in entity.provides:
        effective = ref.port_name if ref.port_name else ref.name
        if effective == port_name:
            return ("provides", ref)
    return None


def _build_edges_from_connect(
    conn: ConnectDef,
    child_node_map: dict[str, VizNode],
    sub_entity_map: dict[str, Component | System | UserDef],
    channel_node_map: dict[str, VizNode],
) -> list[VizEdge]:
    """Build :class:`VizEdge` instances from a :class:`ConnectDef`.

    For a direct connect (no channel), returns at most one edge.  For a
    channel connect, returns up to two edges: one from the source to the
    channel's input port and one from the channel's output port to the
    destination.  One-sided connects produce a single edge to or from the
    channel.

    Returns an empty list when entity references cannot be resolved or both
    sides of a channel connect are absent.
    """
    if conn.channel is None:
        edge = _build_direct_edge(conn, child_node_map, sub_entity_map)
        return [edge] if edge is not None else []

    ch_node = channel_node_map.get(conn.channel)
    if ch_node is None:
        return []

    ch_in_port = next((p for p in ch_node.ports if p.direction == "requires"), None)
    ch_out_port = next((p for p in ch_node.ports if p.direction == "provides"), None)

    edges: list[VizEdge] = []

    # src entity → channel input
    if conn.src_entity is not None and conn.src_port is not None and ch_in_port is not None:
        src_sub = sub_entity_map.get(conn.src_entity)
        src_node = child_node_map.get(conn.src_entity)
        if src_sub is not None and src_node is not None:
            src_result = _find_ref_by_port_name(src_sub, conn.src_port)
            if src_result is not None:
                src_dir, src_ref = src_result
                src_port_id = _find_port_id(src_node, src_dir, src_ref)
                if src_port_id is None:
                    p = _make_port(src_node.id, src_dir, src_ref)
                    src_node.ports.append(p)
                    src_port_id = p.id
                edges.append(
                    VizEdge(
                        id=f"edge.{src_port_id}--{ch_in_port.id}",
                        source_port_id=src_port_id,
                        target_port_id=ch_in_port.id,
                        label=_iref_label(src_ref),
                        interface_name=src_ref.name,
                        interface_version=src_ref.version,
                        protocol=conn.protocol,
                        is_async=conn.is_async,
                        description=conn.description,
                    )
                )

    # channel output → dst entity
    if conn.dst_entity is not None and conn.dst_port is not None and ch_out_port is not None:
        dst_sub = sub_entity_map.get(conn.dst_entity)
        dst_node = child_node_map.get(conn.dst_entity)
        if dst_sub is not None and dst_node is not None:
            dst_result = _find_ref_by_port_name(dst_sub, conn.dst_port)
            if dst_result is not None:
                dst_dir, dst_ref = dst_result
                dst_port_id = _find_port_id(dst_node, dst_dir, dst_ref)
                if dst_port_id is None:
                    p = _make_port(dst_node.id, dst_dir, dst_ref)
                    dst_node.ports.append(p)
                    dst_port_id = p.id
                edges.append(
                    VizEdge(
                        id=f"edge.{ch_out_port.id}--{dst_port_id}",
                        source_port_id=ch_out_port.id,
                        target_port_id=dst_port_id,
                        label=_iref_label(dst_ref),
                        interface_name=dst_ref.name,
                        interface_version=dst_ref.version,
                        protocol=conn.protocol,
                        is_async=conn.is_async,
                        description=conn.description,
                    )
                )

    return edges


def _build_direct_edge(
    conn: ConnectDef,
    child_node_map: dict[str, VizNode],
    sub_entity_map: dict[str, Component | System | UserDef],
) -> VizEdge | None:
    """Build a single :class:`VizEdge` for a direct (no-channel) connect.

    Returns ``None`` when either side is unspecified or unresolvable.
    """
    if conn.src_entity is None or conn.src_port is None:
        return None
    if conn.dst_entity is None or conn.dst_port is None:
        return None

    src_sub = sub_entity_map.get(conn.src_entity)
    dst_sub = sub_entity_map.get(conn.dst_entity)
    if src_sub is None or dst_sub is None:
        return None

    src_result = _find_ref_by_port_name(src_sub, conn.src_port)
    dst_result = _find_ref_by_port_name(dst_sub, conn.dst_port)
    if src_result is None or dst_result is None:
        return None

    src_dir, src_ref = src_result
    dst_dir, dst_ref = dst_result

    src_node = child_node_map.get(conn.src_entity)
    dst_node = child_node_map.get(conn.dst_entity)
    if src_node is None or dst_node is None:
        return None

    src_port_id = _find_port_id(src_node, src_dir, src_ref)
    dst_port_id = _find_port_id(dst_node, dst_dir, dst_ref)

    if src_port_id is None:
        p = _make_port(src_node.id, src_dir, src_ref)
        src_node.ports.append(p)
        src_port_id = p.id

    if dst_port_id is None:
        p = _make_port(dst_node.id, dst_dir, dst_ref)
        dst_node.ports.append(p)
        dst_port_id = p.id

    label = _iref_label(src_ref)
    return VizEdge(
        id=f"edge.{src_port_id}--{dst_port_id}",
        source_port_id=src_port_id,
        target_port_id=dst_port_id,
        label=label,
        interface_name=src_ref.name,
        interface_version=src_ref.version,
        protocol=conn.protocol,
        is_async=conn.is_async,
        description=conn.description,
    )


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


def _should_expand(entity: Component | System | UserDef) -> bool:
    """Return ``True`` if *entity* should be rendered as an expanded boundary.

    Non-external components and systems that contain at least one direct child
    (component, sub-system, or user) are expanded so their internal structure
    is visible.  External entities and leaf entities (no inner children) are
    rendered as opaque nodes.  :class:`~archml.model.entities.UserDef` nodes
    are always leaf.
    """
    if isinstance(entity, UserDef) or entity.is_external:
        return False
    if isinstance(entity, Component):
        return bool(entity.components)
    # System
    return bool(entity.components) or bool(entity.systems) or bool(entity.users)


# Type alias used locally: maps an exposed port name to the leaf VizNode,
# leaf model entity, and the effective port name on that leaf entity.
_ExposeMap = dict[str, tuple[VizNode, "Component | System | UserDef", str]]


def _build_recursive_boundary(
    entity: Component | System,
    entity_path: str,
) -> tuple[VizBoundary, list[VizEdge], _ExposeMap]:
    """Build a :class:`VizBoundary` for *entity*, recursively expanding children.

    Children that themselves have sub-entities are expanded into nested
    :class:`VizBoundary` instances; leaf children become opaque
    :class:`VizNode` instances.  Channel nodes are created for every named
    channel referenced in the entity's ``connect`` statements.

    Port and interface resolution follows ``expose`` chains at arbitrary depth
    so that a connect statement referencing an exposed port on an expanded child
    is correctly routed to the actual leaf component.

    Returns:
        A three-tuple ``(boundary, edges, expose_map)`` where

        - *boundary* is the :class:`VizBoundary` for this entity.
        - *edges* is the complete list of :class:`VizEdge` instances produced
          inside this entity at all levels (recursively).
        - *expose_map* maps every name exposed by *entity* (via its ``expose``
          declarations) to the ``(leaf_node, leaf_entity, leaf_port)`` triple
          needed by the parent to build edges that target this entity's ports.
    """
    root_id = _make_id(entity_path)

    child_entities: list[Component | System | UserDef] = list(entity.components)
    if isinstance(entity, System):
        child_entities += list(entity.systems) + list(entity.users)

    sub_entity_map: dict[str, Component | System | UserDef] = {}
    opaque_node_map: dict[str, VizNode] = {}
    child_boundary_map: dict[str, VizBoundary] = {}
    child_expose_maps: dict[str, _ExposeMap] = {}
    all_edges: list[VizEdge] = []

    for child in child_entities:
        child_path = f"{entity_path}::{child.name}"
        sub_entity_map[child.name] = child
        if _should_expand(child):
            child_bnd, child_edges, child_expose_map = _build_recursive_boundary(child, child_path)  # type: ignore[arg-type]
            child_boundary_map[child.name] = child_bnd
            child_expose_maps[child.name] = child_expose_map
            all_edges.extend(child_edges)
        else:
            opaque_node_map[child.name] = _make_child_node(child, child_path)

    # Channel nodes — use expose-chain-aware label resolution.
    channel_node_map = _collect_channel_nodes_resolve(
        entity.connects, root_id, sub_entity_map, opaque_node_map, child_expose_maps
    )

    all_children: list[VizNode | VizBoundary] = [
        *opaque_node_map.values(),
        *child_boundary_map.values(),
        *channel_node_map.values(),
    ]
    boundary = VizBoundary(
        id=root_id,
        label=entity.name,
        title=entity.title,
        kind="component" if isinstance(entity, Component) else "system",
        entity_path=entity_path,
        description=entity.description,
        tags=list(entity.tags),
        ports=_make_ports(root_id, entity),
        children=all_children,
    )

    # Edges from this entity's connect statements using expose-chain resolution.
    seen: set[tuple[str, str]] = set()
    for conn in entity.connects:
        for edge in _build_edges_from_connect_resolve(
            conn, opaque_node_map, sub_entity_map, channel_node_map, child_expose_maps
        ):
            key = (edge.source_port_id, edge.target_port_id)
            if key not in seen:
                seen.add(key)
                all_edges.append(edge)

    # Build the expose map for this entity's own exposed ports.
    expose_map: _ExposeMap = {}
    for exp in entity.exposes:
        effective = exp.as_name if exp.as_name else exp.port
        child_entity = sub_entity_map.get(exp.entity)
        if child_entity is None:
            continue
        if exp.entity in child_expose_maps:
            # Child is itself expanded — follow its expose map.
            inner = child_expose_maps[exp.entity].get(exp.port)
            if inner is not None:
                expose_map[effective] = inner
        else:
            child_node = opaque_node_map.get(exp.entity)
            if child_node is not None:
                expose_map[effective] = (child_node, child_entity, exp.port)

    return boundary, all_edges, expose_map


def _resolve_iface_label(
    entity_name: str,
    port_name: str,
    sub_entity_map: dict[str, Component | System | UserDef],
    child_expose_maps: dict[str, _ExposeMap],
) -> str | None:
    """Return the interface label for *entity_name.port_name*, following expose chains."""
    if entity_name in child_expose_maps:
        result = child_expose_maps[entity_name].get(port_name)
        if result is not None:
            _, leaf_entity, leaf_port = result
            ref_result = _find_ref_by_port_name(leaf_entity, leaf_port)
            if ref_result is not None:
                return _iref_label(ref_result[1])
    else:
        sub = sub_entity_map.get(entity_name)
        if sub is not None:
            ref_result = _find_ref_by_port_name(sub, port_name)
            if ref_result is not None:
                return _iref_label(ref_result[1])
    return None


def _collect_channel_nodes_resolve(
    connects: list[ConnectDef],
    root_id: str,
    sub_entity_map: dict[str, Component | System | UserDef],
    opaque_node_map: dict[str, VizNode],
    child_expose_maps: dict[str, _ExposeMap],
) -> dict[str, VizNode]:
    """Like :func:`_collect_channel_nodes` but resolves labels through expose chains."""
    channel_interfaces: dict[str, str | None] = {}
    for conn in connects:
        if conn.channel is None:
            continue
        ch = conn.channel
        if ch not in channel_interfaces:
            channel_interfaces[ch] = None
        if channel_interfaces[ch] is not None:
            continue
        if conn.src_entity and conn.src_port:
            label = _resolve_iface_label(conn.src_entity, conn.src_port, sub_entity_map, child_expose_maps)
            if label:
                channel_interfaces[ch] = label
        if channel_interfaces[ch] is None and conn.dst_entity and conn.dst_port:
            label = _resolve_iface_label(conn.dst_entity, conn.dst_port, sub_entity_map, child_expose_maps)
            if label:
                channel_interfaces[ch] = label

    channel_nodes: dict[str, VizNode] = {}
    for ch_name, iface_label in channel_interfaces.items():
        ch_id = f"{root_id}.channel.{ch_name}"
        display_iface = iface_label or ch_name
        ports = [
            VizPort(
                id=f"{ch_id}.in",
                node_id=ch_id,
                interface_name=display_iface,
                interface_version=None,
                direction="requires",
            ),
            VizPort(
                id=f"{ch_id}.out",
                node_id=ch_id,
                interface_name=display_iface,
                interface_version=None,
                direction="provides",
            ),
        ]
        channel_nodes[ch_name] = VizNode(
            id=ch_id, label=ch_name, title=iface_label, kind="channel", entity_path="", ports=ports
        )
    return channel_nodes


def _build_edges_from_connect_resolve(
    conn: ConnectDef,
    opaque_node_map: dict[str, VizNode],
    sub_entity_map: dict[str, Component | System | UserDef],
    channel_node_map: dict[str, VizNode],
    child_expose_maps: dict[str, _ExposeMap],
) -> list[VizEdge]:
    """Build edges from a connect statement using expose-chain resolution.

    Used inside :func:`_build_recursive_boundary` to build edges that may
    reference exposed ports on expanded child entities.
    """

    def resolve_side(
        entity_name: str | None, port_name: str | None
    ) -> tuple[VizNode, Component | System | UserDef, str] | None:
        if entity_name is None or port_name is None:
            return None
        if entity_name in child_expose_maps:
            result = child_expose_maps[entity_name].get(port_name)
            return result  # (leaf_node, leaf_entity, leaf_port) or None
        node = opaque_node_map.get(entity_name)
        entity = sub_entity_map.get(entity_name)
        if node is not None and entity is not None:
            return (node, entity, port_name)
        return None

    return _build_edges_for_connect(conn, channel_node_map, resolve_side)


def _resolve_endpoint(
    entity_name: str,
    port_name: str,
    opaque_node_map: dict[str, VizNode],
    all_entity_map: dict[str, Component | System | UserDef],
    expanded_expose_maps: dict[str, _ExposeMap],
) -> tuple[VizNode, Component | System | UserDef, str] | None:
    """Resolve an ``entity.port`` reference to ``(leaf_node, leaf_entity, leaf_port)``.

    For expanded entities the resolution uses the pre-computed expose map that
    follows the full expose chain to the actual leaf component.  For opaque
    entities the entity's own :class:`VizNode` is returned directly.
    """
    if entity_name in expanded_expose_maps:
        return expanded_expose_maps[entity_name].get(port_name)
    entity = all_entity_map.get(entity_name)
    node = opaque_node_map.get(entity_name)
    if entity is not None and node is not None:
        return (node, entity, port_name)
    return None


def _build_edges_from_connect_expanded(
    conn: ConnectDef,
    opaque_node_map: dict[str, VizNode],
    all_entity_map: dict[str, Component | System | UserDef],
    channel_node_map: dict[str, VizNode],
    expanded_expose_maps: dict[str, _ExposeMap],
) -> list[VizEdge]:
    """Build edges for the all-diagram, resolving exposed ports through the full chain."""

    def resolve_side(
        entity_name: str | None, port_name: str | None
    ) -> tuple[VizNode, Component | System | UserDef, str] | None:
        if entity_name is None or port_name is None:
            return None
        return _resolve_endpoint(entity_name, port_name, opaque_node_map, all_entity_map, expanded_expose_maps)

    return _build_edges_for_connect(conn, channel_node_map, resolve_side)


def _build_edges_for_connect(
    conn: ConnectDef,
    channel_node_map: dict[str, VizNode],
    resolve_side: Callable[[str | None, str | None], tuple[VizNode, Component | System | UserDef, str] | None],
) -> list[VizEdge]:
    """Core edge-building logic shared between all connect resolution paths.

    *resolve_side* is called with ``(entity_name, port_name)`` and must return
    ``(leaf_node, leaf_entity, leaf_port)`` or ``None`` when resolution fails.
    """
    if conn.channel is None:
        if conn.src_entity is None or conn.src_port is None:
            return []
        if conn.dst_entity is None or conn.dst_port is None:
            return []
        src = resolve_side(conn.src_entity, conn.src_port)
        dst = resolve_side(conn.dst_entity, conn.dst_port)
        if src is None or dst is None:
            return []
        src_node, src_sub, src_eff = src
        dst_node, dst_sub, dst_eff = dst
        src_result = _find_ref_by_port_name(src_sub, src_eff)
        dst_result = _find_ref_by_port_name(dst_sub, dst_eff)
        if src_result is None or dst_result is None:
            return []
        src_dir, src_ref = src_result
        dst_dir, dst_ref = dst_result
        src_port_id = _find_port_id(src_node, src_dir, src_ref)
        if src_port_id is None:
            p = _make_port(src_node.id, src_dir, src_ref)
            src_node.ports.append(p)
            src_port_id = p.id
        dst_port_id = _find_port_id(dst_node, dst_dir, dst_ref)
        if dst_port_id is None:
            p = _make_port(dst_node.id, dst_dir, dst_ref)
            dst_node.ports.append(p)
            dst_port_id = p.id
        return [
            VizEdge(
                id=f"edge.{src_port_id}--{dst_port_id}",
                source_port_id=src_port_id,
                target_port_id=dst_port_id,
                label=_iref_label(src_ref),
                interface_name=src_ref.name,
                interface_version=src_ref.version,
                protocol=conn.protocol,
                is_async=conn.is_async,
                description=conn.description,
            )
        ]

    ch_node = channel_node_map.get(conn.channel)
    if ch_node is None:
        return []

    ch_in_port = next((p for p in ch_node.ports if p.direction == "requires"), None)
    ch_out_port = next((p for p in ch_node.ports if p.direction == "provides"), None)

    edges: list[VizEdge] = []

    if conn.src_entity is not None and conn.src_port is not None and ch_in_port is not None:
        src = resolve_side(conn.src_entity, conn.src_port)
        if src is not None:
            src_node, src_sub, src_eff = src
            src_result = _find_ref_by_port_name(src_sub, src_eff)
            if src_result is not None:
                src_dir, src_ref = src_result
                src_port_id = _find_port_id(src_node, src_dir, src_ref)
                if src_port_id is None:
                    p = _make_port(src_node.id, src_dir, src_ref)
                    src_node.ports.append(p)
                    src_port_id = p.id
                edges.append(
                    VizEdge(
                        id=f"edge.{src_port_id}--{ch_in_port.id}",
                        source_port_id=src_port_id,
                        target_port_id=ch_in_port.id,
                        label=_iref_label(src_ref),
                        interface_name=src_ref.name,
                        interface_version=src_ref.version,
                        protocol=conn.protocol,
                        is_async=conn.is_async,
                        description=conn.description,
                    )
                )

    if conn.dst_entity is not None and conn.dst_port is not None and ch_out_port is not None:
        dst = resolve_side(conn.dst_entity, conn.dst_port)
        if dst is not None:
            dst_node, dst_sub, dst_eff = dst
            dst_result = _find_ref_by_port_name(dst_sub, dst_eff)
            if dst_result is not None:
                dst_dir, dst_ref = dst_result
                dst_port_id = _find_port_id(dst_node, dst_dir, dst_ref)
                if dst_port_id is None:
                    p = _make_port(dst_node.id, dst_dir, dst_ref)
                    dst_node.ports.append(p)
                    dst_port_id = p.id
                edges.append(
                    VizEdge(
                        id=f"edge.{ch_out_port.id}--{dst_port_id}",
                        source_port_id=ch_out_port.id,
                        target_port_id=dst_port_id,
                        label=_iref_label(dst_ref),
                        interface_name=dst_ref.name,
                        interface_version=dst_ref.version,
                        protocol=conn.protocol,
                        is_async=conn.is_async,
                        description=conn.description,
                    )
                )
    return edges
