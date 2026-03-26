# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the abstract visualization topology model and its builder."""

from archml.model.entities import ArchFile, Component, ConnectDef, ExposeDef, InterfaceRef, System, UserDef
from archml.views.topology import (
    VizBoundary,
    VizNode,
    VizPort,
    build_viz_diagram,
    build_viz_diagram_all,
    collect_all_ports,
)

# ###############
# Helpers
# ###############


def _iref(name: str, version: str | None = None) -> InterfaceRef:
    return InterfaceRef(name=name, version=version)


def _connect(
    src_entity: str,
    src_port: str,
    dst_entity: str,
    dst_port: str,
    channel: str | None = None,
) -> ConnectDef:
    return ConnectDef(
        src_entity=src_entity,
        src_port=src_port,
        channel=channel,
        dst_entity=dst_entity,
        dst_port=dst_port,
    )


def _port_ids(ports: list[VizPort]) -> set[str]:
    return {p.id for p in ports}


def _node_ids(nodes: list[VizNode]) -> set[str]:
    return {n.id for n in nodes}


def _child_ids(boundary: VizBoundary) -> set[str]:
    return {c.id for c in boundary.children}


# ###############
# VizDiagram — root boundary
# ###############


def test_root_boundary_id_from_entity_name() -> None:
    """Root boundary ID is derived from the entity name."""
    comp = Component(name="Worker")
    diag = build_viz_diagram(comp)
    assert diag.root.id == "Worker"


def test_root_boundary_id_uses_qualified_name() -> None:
    """When qualified_name is set it is preferred over plain name."""
    comp = Component(name="Worker", qualified_name="System::Worker")
    diag = build_viz_diagram(comp)
    assert diag.root.id == "System__Worker"


def test_root_boundary_coloncolon_replaced_by_double_underscore() -> None:
    """``::`` separators in entity paths are replaced by ``__`` in IDs."""
    comp = Component(name="A", qualified_name="X::Y::A")
    diag = build_viz_diagram(comp)
    assert diag.root.id == "X__Y__A"


def test_root_boundary_label() -> None:
    """Root boundary label is the entity name."""
    comp = Component(name="order_service")
    diag = build_viz_diagram(comp)
    assert diag.root.label == "order_service"


def test_root_boundary_kind_component() -> None:
    comp = Component(name="C")
    diag = build_viz_diagram(comp)
    assert diag.root.kind == "component"


def test_root_boundary_kind_system() -> None:
    sys = System(name="S")
    diag = build_viz_diagram(sys)
    assert diag.root.kind == "system"


def test_root_boundary_description_propagated() -> None:
    comp = Component(name="C", description="Does things")
    diag = build_viz_diagram(comp)
    assert diag.root.description == "Does things"


def test_root_boundary_tags_empty() -> None:
    comp = Component(name="C")
    diag = build_viz_diagram(comp)
    assert diag.root.tags == []


# ###############
# VizDiagram — metadata
# ###############


def test_diagram_id_prefixed() -> None:
    comp = Component(name="Worker")
    diag = build_viz_diagram(comp)
    assert diag.id == "diagram.Worker"


def test_diagram_title_from_entity_name() -> None:
    comp = Component(name="Worker")
    diag = build_viz_diagram(comp)
    assert diag.title == "Worker"


def test_diagram_description_none_when_absent() -> None:
    comp = Component(name="C")
    diag = build_viz_diagram(comp)
    assert diag.description is None


# ###############
# Root boundary — child nodes
# ###############


def test_child_component_becomes_viz_node() -> None:
    """Each direct component child becomes a VizNode inside the root boundary."""
    child = Component(name="Alpha")
    parent = Component(name="Parent", components=[child])
    diag = build_viz_diagram(parent)
    ids = _child_ids(diag.root)
    assert "Parent__Alpha" in ids


def test_child_system_becomes_viz_node() -> None:
    """Each direct sub-system becomes a VizNode inside the root boundary."""
    sub = System(name="Sub")
    parent = System(name="Root", systems=[sub])
    diag = build_viz_diagram(parent)
    ids = _child_ids(diag.root)
    assert "Root__Sub" in ids


def test_child_node_kind_component() -> None:
    child = Component(name="C")
    parent = System(name="S", components=[child])
    diag = build_viz_diagram(parent)
    node = next(n for n in diag.root.children if isinstance(n, VizNode) and n.label == "C")
    assert node.kind == "component"


def test_child_node_kind_system() -> None:
    sub = System(name="Sub")
    parent = System(name="Root", systems=[sub])
    diag = build_viz_diagram(parent)
    node = next(n for n in diag.root.children if isinstance(n, VizNode) and n.label == "Sub")
    assert node.kind == "system"


def test_external_child_node_kind() -> None:
    """An external component child gets kind 'external_component'."""
    ext_comp = Component(name="ExtC", is_external=True)
    parent = System(name="S", components=[ext_comp])
    diag = build_viz_diagram(parent)
    node = next(n for n in diag.root.children if isinstance(n, VizNode) and n.label == "ExtC")
    assert node.kind == "external_component"


def test_child_node_entity_path() -> None:
    child = Component(name="Alpha")
    parent = Component(name="Parent", components=[child])
    diag = build_viz_diagram(parent)
    node = next(n for n in diag.root.children if isinstance(n, VizNode))
    assert node.entity_path == "Parent::Alpha"


def test_child_node_description() -> None:
    child = Component(name="C", description="desc")
    parent = System(name="S", components=[child])
    diag = build_viz_diagram(parent)
    node = next(n for n in diag.root.children if isinstance(n, VizNode))
    assert node.description == "desc"


def test_leaf_entity_has_no_children() -> None:
    comp = Component(name="Leaf")
    diag = build_viz_diagram(comp)
    assert diag.root.children == []


# ###############
# Ports — root boundary
# ###############


def test_root_boundary_requires_port() -> None:
    """Each ``requires`` declaration on the focus entity becomes a requires port."""
    comp = Component(name="C", requires=[_iref("DataFeed")])
    diag = build_viz_diagram(comp)
    ports = {p.interface_name: p for p in diag.root.ports}
    assert "DataFeed" in ports
    assert ports["DataFeed"].direction == "requires"


def test_root_boundary_provides_port() -> None:
    """Each ``provides`` declaration on the focus entity becomes a provides port."""
    comp = Component(name="C", provides=[_iref("Result")])
    diag = build_viz_diagram(comp)
    ports = {p.interface_name: p for p in diag.root.ports}
    assert "Result" in ports
    assert ports["Result"].direction == "provides"


def test_root_port_versioned_interface() -> None:
    comp = Component(name="C", provides=[_iref("API", version="v2")])
    diag = build_viz_diagram(comp)
    port = diag.root.ports[0]
    assert port.interface_version == "v2"
    assert "v2" in port.id


def test_root_port_node_id_matches_root_id() -> None:
    comp = Component(name="C", requires=[_iref("X")])
    diag = build_viz_diagram(comp)
    assert diag.root.ports[0].node_id == diag.root.id


# ###############
# Ports — child nodes
# ###############


def test_child_node_ports_created_from_requires_provides() -> None:
    """A child node carries ports for all its requires and provides."""
    child = Component(name="W", requires=[_iref("In")], provides=[_iref("Out")])
    parent = System(name="S", components=[child])
    diag = build_viz_diagram(parent)
    node = next(n for n in diag.root.children if isinstance(n, VizNode))
    directions = {p.direction for p in node.ports}
    assert "requires" in directions
    assert "provides" in directions


def test_child_port_id_contains_node_id_and_interface() -> None:
    child = Component(name="W", requires=[_iref("Feed")])
    parent = System(name="S", components=[child])
    diag = build_viz_diagram(parent)
    node = next(n for n in diag.root.children if isinstance(n, VizNode))
    port = node.ports[0]
    assert node.id in port.id
    assert "Feed" in port.id


# ###############
# Peripheral nodes — terminals
# ###############


def test_requires_terminal_node_created() -> None:
    """The focus entity's ``requires`` interfaces become terminal nodes."""
    comp = Component(name="C", requires=[_iref("OrderRequest")])
    diag = build_viz_diagram(comp)
    ids = _node_ids(diag.peripheral_nodes)
    assert "terminal.req.OrderRequest" in ids


def test_provides_terminal_node_created() -> None:
    """The focus entity's ``provides`` interfaces become terminal nodes."""
    comp = Component(name="C", provides=[_iref("OrderConfirmation")])
    diag = build_viz_diagram(comp)
    ids = _node_ids(diag.peripheral_nodes)
    assert "terminal.prov.OrderConfirmation" in ids


def test_terminal_node_kind() -> None:
    comp = Component(name="C", requires=[_iref("X")])
    diag = build_viz_diagram(comp)
    terminal = diag.peripheral_nodes[0]
    assert terminal.kind == "terminal"


def test_terminal_node_has_one_port() -> None:
    comp = Component(name="C", requires=[_iref("X")])
    diag = build_viz_diagram(comp)
    terminal = diag.peripheral_nodes[0]
    assert len(terminal.ports) == 1


def test_terminal_port_direction_faces_boundary() -> None:
    """Terminal port direction is the opposite of the interface direction so the anchor faces the boundary.

    A ``requires`` terminal sits to the left and acts as an external provider:
    its port direction is ``"provides"`` (anchored to the right edge, closest to the boundary).
    A ``provides`` terminal sits to the right and acts as an external consumer:
    its port direction is ``"requires"`` (anchored to the left edge, closest to the boundary).
    """
    comp = Component(name="C", requires=[_iref("In")], provides=[_iref("Out")])
    diag = build_viz_diagram(comp)
    by_id = {n.id: n for n in diag.peripheral_nodes}
    req_terminal = by_id["terminal.req.In"]
    prov_terminal = by_id["terminal.prov.Out"]
    assert req_terminal.ports[0].direction == "provides"
    assert prov_terminal.ports[0].direction == "requires"


def test_versioned_terminal_label_includes_version() -> None:
    comp = Component(name="C", provides=[_iref("API", version="v2")])
    diag = build_viz_diagram(comp)
    ids = _node_ids(diag.peripheral_nodes)
    assert "terminal.prov.API@v2" in ids


def test_no_terminals_for_leaf_without_interfaces() -> None:
    comp = Component(name="Isolated")
    diag = build_viz_diagram(comp)
    # No terminals; no external nodes either.
    assert diag.peripheral_nodes == []


# ###############
# Edges — connect-based
# ###############


def test_edge_created_for_connect_statement() -> None:
    """A full channel connect produces two edges: src→channel and channel→dst."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    parent = System(
        name="S",
        connects=[_connect("B", "IFace", "A", "IFace", channel="ch")],
        components=[a, b],
    )
    diag = build_viz_diagram(parent)
    # Two edges: B → channel and channel → A.
    assert len(diag.edges) == 2


def test_channel_node_appears_as_child() -> None:
    """A named channel in a connect becomes a VizNode child of the root boundary."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    parent = System(
        name="S",
        connects=[_connect("B", "IFace", "A", "IFace", channel="ch")],
        components=[a, b],
    )
    diag = build_viz_diagram(parent)
    child_kinds = {c.kind for c in diag.root.children if isinstance(c, VizNode)}
    assert "channel" in child_kinds
    channel_node = next(c for c in diag.root.children if isinstance(c, VizNode) and c.kind == "channel")
    assert channel_node.label == "ch"


def test_one_sided_connect_creates_channel_edge() -> None:
    """A one-sided connect (src → channel, no dst) produces one edge into the channel."""
    a = Component(name="A", provides=[_iref("IFace")])
    parent = System(
        name="S",
        connects=[ConnectDef(src_entity="A", src_port="IFace", channel="ch")],
        components=[a],
    )
    diag = build_viz_diagram(parent)
    # One edge: A → channel (no dst edge since no dst entity).
    assert len(diag.edges) == 1
    all_ports = collect_all_ports(diag)
    edge = diag.edges[0]
    src_port = all_ports[edge.source_port_id]
    assert src_port.node_id == "S__A"
    tgt_port = all_ports[edge.target_port_id]
    assert tgt_port.direction == "requires"  # channel in-port


def test_one_sided_dst_connect_creates_channel_edge() -> None:
    """A one-sided connect (channel → dst, no src) produces one edge from the channel."""
    b = Component(name="B", requires=[_iref("IFace")])
    parent = System(
        name="S",
        connects=[ConnectDef(channel="ch", dst_entity="B", dst_port="IFace")],
        components=[b],
    )
    diag = build_viz_diagram(parent)
    # One edge: channel → B (no src edge since no src entity).
    assert len(diag.edges) == 1
    all_ports = collect_all_ports(diag)
    edge = diag.edges[0]
    src_port = all_ports[edge.source_port_id]
    assert src_port.direction == "provides"  # channel out-port
    tgt_port = all_ports[edge.target_port_id]
    assert tgt_port.node_id == "S__B"


def test_edge_label_is_interface_name() -> None:
    a = Component(name="A", requires=[_iref("PayReq")])
    b = Component(name="B", provides=[_iref("PayReq")])
    parent = System(
        name="S",
        connects=[_connect("B", "PayReq", "A", "PayReq", channel="pay")],
        components=[a, b],
    )
    diag = build_viz_diagram(parent)
    # Both edges carry the interface name as label.
    assert all(e.label == "PayReq" for e in diag.edges)


def test_edge_label_includes_version() -> None:
    a = Component(name="A", requires=[_iref("API", "v2")])
    b = Component(name="B", provides=[_iref("API", "v2")])
    parent = System(
        name="S",
        connects=[ConnectDef(src_entity="B", src_port="API", channel="ch", dst_entity="A", dst_port="API")],
        components=[a, b],
    )
    diag = build_viz_diagram(parent)
    assert all(e.label == "API@v2" for e in diag.edges)


def test_edge_source_port_is_src_entity_port() -> None:
    """First edge (src→channel): source_port_id references the src_entity's port."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    # B is src_entity (provider), A is dst_entity (requirer)
    parent = System(
        name="S",
        connects=[_connect("B", "IFace", "A", "IFace", channel="ch")],
        components=[a, b],
    )
    diag = build_viz_diagram(parent)
    all_ports = collect_all_ports(diag)
    # edges[0] is B → channel
    src_port = all_ports[diag.edges[0].source_port_id]
    assert src_port.direction == "provides"
    assert src_port.interface_name == "IFace"


def test_edge_target_port_is_channel_in_port() -> None:
    """First edge (src→channel): target_port_id is the channel's input (requires) port."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    parent = System(
        name="S",
        connects=[_connect("B", "IFace", "A", "IFace", channel="ch")],
        components=[a, b],
    )
    diag = build_viz_diagram(parent)
    all_ports = collect_all_ports(diag)
    # edges[0] target is the channel's in-port (direction=requires)
    tgt_port = all_ports[diag.edges[0].target_port_id]
    assert tgt_port.direction == "requires"
    assert tgt_port.interface_name == "IFace"


def test_second_edge_target_port_is_dst_entity_port() -> None:
    """Second edge (channel→dst): target_port_id references the dst_entity's port."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    parent = System(
        name="S",
        connects=[_connect("B", "IFace", "A", "IFace", channel="ch")],
        components=[a, b],
    )
    diag = build_viz_diagram(parent)
    all_ports = collect_all_ports(diag)
    # edges[1] is channel → A
    tgt_port = all_ports[diag.edges[1].target_port_id]
    assert tgt_port.direction == "requires"
    assert tgt_port.interface_name == "IFace"
    assert tgt_port.node_id == "S__A"


def test_edge_source_and_target_port_owners() -> None:
    """Channel connect: first edge goes src→channel, second edge goes channel→dst."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    # B is src (provider), A is dst (requirer)
    parent = System(
        name="S",
        connects=[_connect("B", "IFace", "A", "IFace", channel="ch")],
        components=[a, b],
    )
    diag = build_viz_diagram(parent)
    all_ports = collect_all_ports(diag)
    # edges[0]: B.prov → channel.in
    assert all_ports[diag.edges[0].source_port_id].node_id == "S__B"
    channel_node = next(c for c in diag.root.children if isinstance(c, VizNode) and c.kind == "channel")
    assert all_ports[diag.edges[0].target_port_id].node_id == channel_node.id
    # edges[1]: channel.out → A.req
    assert all_ports[diag.edges[1].source_port_id].node_id == channel_node.id
    assert all_ports[diag.edges[1].target_port_id].node_id == "S__A"


def test_multiple_edges_from_multiple_connects() -> None:
    """Two channel connects (different channels) each produce two edges = four total."""
    a = Component(name="A", requires=[_iref("X"), _iref("Y")])
    b = Component(name="B", provides=[_iref("X")])
    c = Component(name="C", provides=[_iref("Y")])
    parent = System(
        name="S",
        connects=[
            _connect("B", "X", "A", "X", channel="ch1"),
            _connect("C", "Y", "A", "Y", channel="ch2"),
        ],
        components=[a, b, c],
    )
    diag = build_viz_diagram(parent)
    # 2 channels × 2 edges each = 4 edges.
    assert len(diag.edges) == 4


def test_external_component_connected() -> None:
    """An external component (is_external=True) can be wired via connect."""
    stripe = Component(name="StripeAPI", is_external=True, requires=[_iref("PaymentRequest")])
    gateway = Component(name="PaymentGateway", provides=[_iref("PaymentRequest")])
    parent = System(
        name="S",
        connects=[_connect("PaymentGateway", "PaymentRequest", "StripeAPI", "PaymentRequest", channel="payment")],
        components=[stripe, gateway],
    )
    diag = build_viz_diagram(parent)
    # Both entity nodes and the channel node are inside the boundary.
    child_labels = {c.label for c in diag.root.children}
    assert "StripeAPI" in child_labels
    assert "PaymentGateway" in child_labels
    assert "payment" in child_labels
    # Two edges: gateway → channel, channel → stripe.
    assert len(diag.edges) == 2
    stripe_node = next(c for c in diag.root.children if c.label == "StripeAPI")
    assert isinstance(stripe_node, VizNode)
    assert stripe_node.kind == "external_component"


def test_child_component_not_in_peripheral_nodes() -> None:
    """Direct children of the focus entity never appear in peripheral_nodes."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    parent = System(
        name="S",
        connects=[_connect("B", "IFace", "A", "IFace", channel="ch")],
        components=[a, b],
    )
    diag = build_viz_diagram(parent)
    peripheral_labels = {n.label for n in diag.peripheral_nodes}
    assert "A" not in peripheral_labels
    assert "B" not in peripheral_labels


def test_one_provider_multiple_requirers_creates_n_edges() -> None:
    """One provider to N requirers through the same channel: 1 provider→channel + N channel→requirer edges."""
    a = Component(name="A", requires=[_iref("X")])
    b = Component(name="B", requires=[_iref("X")])
    c = Component(name="C", provides=[_iref("X")])
    parent = System(
        name="S",
        connects=[
            _connect("C", "X", "A", "X", channel="ch"),
            _connect("C", "X", "B", "X", channel="ch"),
        ],
        components=[a, b, c],
    )
    diag = build_viz_diagram(parent)
    # C→ch (deduplicated), ch→A, ch→B = 3 edges.
    assert len(diag.edges) == 3


# ###############
# Terminal boundary edges
# ###############


def test_leaf_component_terminal_edges_produced() -> None:
    """A leaf component with requires/provides produces edges connecting terminals to boundary."""
    comp = Component(name="B", requires=[_iref("Simple")], provides=[_iref("OrderConfirmation")])
    diag = build_viz_diagram(comp)
    # One edge per interface: terminal.req→boundary.req and boundary.prov→terminal.prov.
    assert len(diag.edges) == 2


def test_leaf_component_requires_terminal_edge_direction() -> None:
    """The requires terminal is the source and the root boundary port is the target."""
    comp = Component(name="B", requires=[_iref("Simple")])
    diag = build_viz_diagram(comp)
    assert len(diag.edges) == 1
    edge = diag.edges[0]
    assert edge.source_port_id == "terminal.req.Simple.port"
    assert edge.target_port_id == "B.req.Simple"


def test_leaf_component_provides_terminal_edge_direction() -> None:
    """The root boundary port is the source and the provides terminal is the target."""
    comp = Component(name="B", provides=[_iref("OrderConfirmation")])
    diag = build_viz_diagram(comp)
    assert len(diag.edges) == 1
    edge = diag.edges[0]
    assert edge.source_port_id == "B.prov.OrderConfirmation"
    assert edge.target_port_id == "terminal.prov.OrderConfirmation.port"


def test_terminal_boundary_edge_ports_are_resolvable() -> None:
    """All edge port IDs from terminal-boundary edges appear in collect_all_ports."""
    comp = Component(name="B", requires=[_iref("Simple")], provides=[_iref("OrderConfirmation")])
    diag = build_viz_diagram(comp)
    all_ports = collect_all_ports(diag)
    for edge in diag.edges:
        assert edge.source_port_id in all_ports, f"Missing source port {edge.source_port_id}"
        assert edge.target_port_id in all_ports, f"Missing target port {edge.target_port_id}"


def test_system_with_internal_connects_also_has_terminal_edges() -> None:
    """A system with own interfaces AND internal connects gets terminal edges on top of connect edges."""
    a = Component(name="A", provides=[_iref("IFace")])
    b = Component(name="B", requires=[_iref("IFace")])
    sys = System(
        name="S",
        requires=[_iref("In")],
        provides=[_iref("Out")],
        connects=[_connect("A", "IFace", "B", "IFace", channel="ch")],
        components=[a, b],
    )
    diag = build_viz_diagram(sys)
    # 2 connect edges + 2 terminal edges (In and Out).
    assert len(diag.edges) == 4
    all_ports = collect_all_ports(diag)
    for edge in diag.edges:
        assert edge.source_port_id in all_ports
        assert edge.target_port_id in all_ports


# ###############
# collect_all_ports
# ###############


def test_collect_all_ports_includes_root_ports() -> None:
    comp = Component(name="C", requires=[_iref("X")], provides=[_iref("Y")])
    diag = build_viz_diagram(comp)
    all_ports = collect_all_ports(diag)
    names = {p.interface_name for p in all_ports.values()}
    assert "X" in names
    assert "Y" in names


def test_collect_all_ports_includes_child_ports() -> None:
    child = Component(name="W", requires=[_iref("Feed")])
    parent = System(name="S", components=[child])
    diag = build_viz_diagram(parent)
    all_ports = collect_all_ports(diag)
    names = {p.interface_name for p in all_ports.values()}
    assert "Feed" in names


def test_collect_all_ports_includes_terminal_ports() -> None:
    comp = Component(name="C", provides=[_iref("Out")])
    diag = build_viz_diagram(comp)
    all_ports = collect_all_ports(diag)
    names = {p.interface_name for p in all_ports.values()}
    assert "Out" in names


def test_collect_all_ports_returns_unique_ids() -> None:
    """All returned port IDs are distinct."""
    a = Component(name="A", requires=[_iref("X")])
    b = Component(name="B", provides=[_iref("X")])
    parent = System(
        name="S",
        connects=[_connect("B", "X", "A", "X", channel="ch")],
        components=[a, b],
    )
    diag = build_viz_diagram(parent)
    all_ports = collect_all_ports(diag)
    assert len(all_ports) == len(set(all_ports))


# ###############
# End-to-end: full e-commerce example
# ###############


def test_ecommerce_system_topology() -> None:
    """Integration test building a topology for the canonical e-commerce example."""
    order_svc = Component(
        name="OrderService",
        requires=[_iref("PaymentRequest"), _iref("InventoryCheck")],
        provides=[_iref("OrderConfirmation")],
    )
    payment_gw = Component(
        name="PaymentGateway",
        provides=[_iref("PaymentRequest")],
        requires=[_iref("StripePayment")],
    )
    stripe = Component(
        name="StripeAPI",
        is_external=True,
        provides=[_iref("StripePayment")],
    )
    inventory = Component(
        name="InventoryManager",
        provides=[_iref("InventoryCheck")],
    )

    ecommerce = System(
        name="ECommerce",
        connects=[
            _connect("PaymentGateway", "PaymentRequest", "OrderService", "PaymentRequest", channel="payment"),
            _connect("InventoryManager", "InventoryCheck", "OrderService", "InventoryCheck", channel="inventory"),
            _connect("StripeAPI", "StripePayment", "PaymentGateway", "StripePayment", channel="stripe"),
        ],
        components=[order_svc, payment_gw, inventory, stripe],
    )

    diag = build_viz_diagram(ecommerce)

    # Root boundary is ECommerce.
    assert diag.root.id == "ECommerce"
    assert diag.root.kind == "system"

    # Four entity nodes + three channel nodes inside the boundary.
    child_labels = {c.label for c in diag.root.children if isinstance(c, VizNode)}
    assert "OrderService" in child_labels
    assert "PaymentGateway" in child_labels
    assert "InventoryManager" in child_labels
    assert "StripeAPI" in child_labels
    assert "payment" in child_labels
    assert "inventory" in child_labels
    assert "stripe" in child_labels

    # StripeAPI is an external_component child (not peripheral).
    stripe_node = next(c for c in diag.root.children if c.label == "StripeAPI")
    assert isinstance(stripe_node, VizNode)
    assert stripe_node.kind == "external_component"

    # Three channel connects × 2 edges each = 6 edges.
    assert len(diag.edges) == 6
    edge_labels = {e.label for e in diag.edges}
    assert "PaymentRequest" in edge_labels
    assert "InventoryCheck" in edge_labels

    # Stripe channel produces two edges.
    stripe_edges = [e for e in diag.edges if "StripePayment" in e.label]
    assert len(stripe_edges) == 2

    # All ports resolvable.
    all_ports = collect_all_ports(diag)
    for edge in diag.edges:
        assert edge.source_port_id in all_ports
        assert edge.target_port_id in all_ports


# ###############
# User nodes
# ###############


def test_user_as_child_node_of_system_has_kind_user() -> None:
    """A UserDef inside a System becomes a child VizNode with kind 'user'."""
    customer = UserDef(
        name="Customer",
        requires=[InterfaceRef(name="OrderConfirmation")],
        provides=[InterfaceRef(name="OrderRequest")],
    )
    system = System(name="ECommerce", users=[customer])
    diag = build_viz_diagram(system)
    child_ids = _child_ids(diag.root)
    assert "ECommerce__Customer" in child_ids
    customer_node = next(c for c in diag.root.children if c.id == "ECommerce__Customer")
    assert isinstance(customer_node, VizNode)
    assert customer_node.kind == "user"


def test_external_user_child_has_kind_external_user() -> None:
    """An external UserDef child gets kind 'external_user'."""
    ext_user = UserDef(name="Partner", is_external=True)
    system = System(name="S", users=[ext_user])
    diag = build_viz_diagram(system)
    child_node = next(c for c in diag.root.children if c.label == "Partner")
    assert isinstance(child_node, VizNode)
    assert child_node.kind == "external_user"


def test_user_child_ports_are_built() -> None:
    """Ports are created for a user's requires and provides declarations."""
    customer = UserDef(
        name="Customer",
        requires=[InterfaceRef(name="OrderConfirmation")],
        provides=[InterfaceRef(name="OrderRequest")],
    )
    system = System(name="S", users=[customer])
    diag = build_viz_diagram(system)
    customer_node = next(c for c in diag.root.children if c.label == "Customer")
    assert isinstance(customer_node, VizNode)
    directions = {p.direction for p in customer_node.ports}
    assert "requires" in directions
    assert "provides" in directions


def test_user_connect_creates_edge() -> None:
    """A channel connect involving a user entity creates two edges (src→channel, channel→dst)."""
    customer = UserDef(name="Customer", provides=[InterfaceRef(name="OrderRequest")])
    order_svc = Component(name="OrderService", requires=[InterfaceRef(name="OrderRequest")])
    system = System(
        name="ECommerce",
        connects=[
            ConnectDef(
                src_entity="Customer",
                src_port="OrderRequest",
                channel="order_in",
                dst_entity="OrderService",
                dst_port="OrderRequest",
            )
        ],
        users=[customer],
        components=[order_svc],
    )
    diag = build_viz_diagram(system)
    # Two edges: Customer → channel, channel → OrderService.
    assert len(diag.edges) == 2
    all_ports = collect_all_ports(diag)
    # edges[0]: Customer → channel.in
    edge0 = diag.edges[0]
    assert "Customer" in edge0.source_port_id
    assert all_ports[edge0.source_port_id].node_id == "ECommerce__Customer"
    # edges[1]: channel.out → OrderService
    edge1 = diag.edges[1]
    assert "OrderService" in edge1.target_port_id
    assert all_ports[edge1.target_port_id].node_id == "ECommerce__OrderService"
    # All ports resolvable.
    for edge in diag.edges:
        assert edge.source_port_id in all_ports
        assert edge.target_port_id in all_ports


# ###############
# build_viz_diagram — depth parameter
# ###############


class TestBuildVizDiagramDepth:
    """Tests for the depth parameter of build_viz_diagram."""

    def _nested_system(self) -> System:
        """Return a 3-level hierarchy: System → SubSys → Component."""
        leaf = Component(name="Leaf", provides=[_iref("Data")])
        sub = System(name="Sub", components=[leaf])
        root = System(name="Root", systems=[sub])
        return root

    # depth=0 ---------------------------------------------------------------

    def test_depth_0_root_has_no_children(self) -> None:
        """depth=0 renders the root boundary with no children at all."""
        sys = self._nested_system()
        diag = build_viz_diagram(sys, depth=0)
        assert diag.root.children == []

    def test_depth_0_root_boundary_still_created(self) -> None:
        """depth=0 still creates the root VizBoundary."""
        sys = self._nested_system()
        diag = build_viz_diagram(sys, depth=0)
        assert diag.root.id == "Root"
        assert diag.root.kind == "system"

    def test_depth_0_terminal_nodes_still_present(self) -> None:
        """depth=0 still shows terminal nodes for the entity's own interfaces."""
        comp = Component(name="C", requires=[_iref("In")], provides=[_iref("Out")])
        diag = build_viz_diagram(comp, depth=0)
        ids = _node_ids(diag.peripheral_nodes)
        assert "terminal.req.In" in ids
        assert "terminal.prov.Out" in ids

    def test_depth_0_no_connect_edges(self) -> None:
        """depth=0 produces no edges from connect statements."""
        a = Component(name="A", provides=[_iref("X")])
        b = Component(name="B", requires=[_iref("X")])
        sys = System(
            name="S",
            components=[a, b],
            connects=[ConnectDef(src_entity="A", src_port="X", channel="ch", dst_entity="B", dst_port="X")],
        )
        diag = build_viz_diagram(sys, depth=0)
        assert diag.root.children == []
        # No connect edges, but no terminal edges either (S has no own interfaces).
        assert diag.edges == []

    # depth=1 ---------------------------------------------------------------

    def test_depth_1_direct_children_are_opaque_nodes(self) -> None:
        """depth=1 renders direct children as opaque VizNode instances."""
        sys = self._nested_system()
        diag = build_viz_diagram(sys, depth=1)
        # The direct child 'Sub' should be an opaque VizNode (not a boundary).
        child = next(c for c in diag.root.children if c.label == "Sub")
        assert isinstance(child, VizNode)

    def test_depth_1_non_leaf_child_is_opaque(self) -> None:
        """depth=1 keeps non-leaf children as opaque boxes (does not expand them)."""
        inner = Component(name="Inner")
        outer = System(name="Outer", components=[inner])
        parent = System(name="Parent", systems=[outer])
        diag = build_viz_diagram(parent, depth=1)
        child = next(c for c in diag.root.children if c.label == "Outer")
        assert isinstance(child, VizNode)

    # depth=2 ---------------------------------------------------------------

    def test_depth_2_direct_non_leaf_children_expanded(self) -> None:
        """depth=2 expands direct children that have sub-children into VizBoundary."""
        sys = self._nested_system()
        diag = build_viz_diagram(sys, depth=2)
        # 'Sub' has a child → should become a VizBoundary.
        child = next(c for c in diag.root.children if c.label == "Sub")
        assert isinstance(child, VizBoundary)

    def test_depth_2_grandchildren_are_opaque(self) -> None:
        """depth=2 keeps grandchildren (children of expanded children) as opaque VizNodes."""
        sys = self._nested_system()
        diag = build_viz_diagram(sys, depth=2)
        sub_boundary = next(c for c in diag.root.children if isinstance(c, VizBoundary) and c.label == "Sub")
        grandchild = next(c for c in sub_boundary.children if c.label == "Leaf")
        assert isinstance(grandchild, VizNode)

    def test_depth_2_leaf_direct_children_stay_opaque(self) -> None:
        """depth=2 does not expand leaf children (those without sub-children)."""
        leaf_child = Component(name="Leaf")
        parent = System(name="Parent", components=[leaf_child])
        diag = build_viz_diagram(parent, depth=2)
        child = next(c for c in diag.root.children if c.label == "Leaf")
        assert isinstance(child, VizNode)

    # depth=None (full expansion) -------------------------------------------

    def test_depth_none_fully_expands_all_levels(self) -> None:
        """depth=None (default) expands all levels recursively."""
        sys = self._nested_system()
        diag = build_viz_diagram(sys)
        # 'Sub' has a child → VizBoundary.
        sub_boundary = next(c for c in diag.root.children if isinstance(c, VizBoundary) and c.label == "Sub")
        # 'Leaf' has no sub-children → opaque VizNode inside Sub.
        leaf = next(c for c in sub_boundary.children if c.label == "Leaf")
        assert isinstance(leaf, VizNode)

    def test_depth_none_equals_no_depth_arg(self) -> None:
        """Calling with depth=None is identical to calling without depth."""
        sys = self._nested_system()
        diag_default = build_viz_diagram(sys)
        diag_none = build_viz_diagram(sys, depth=None)

        # Both should expand 'Sub' as a VizBoundary.
        def _child_types(diag: object) -> set[type]:
            import archml.views.topology as topo

            assert isinstance(diag, topo.VizDiagram)
            return {type(c) for c in diag.root.children}

        assert _child_types(diag_default) == _child_types(diag_none)

    # expose-based terminal edges across all depths --------------------------

    def _expose_system(self) -> System:
        """System with no direct requires/provides, only expose declarations.

        Order (exposes A.OrderRequest, exposes B.OrderConfirmation)
          A (requires OrderRequest, provides Simple)
          B (requires Simple, provides OrderConfirmation)
        """
        a = Component(name="A", requires=[_iref("OrderRequest")], provides=[_iref("Simple")])
        b = Component(name="B", requires=[_iref("Simple")], provides=[_iref("OrderConfirmation")])
        return System(
            name="Order",
            components=[a, b],
            exposes=[ExposeDef(entity="A", port="OrderRequest"), ExposeDef(entity="B", port="OrderConfirmation")],
        )

    def test_expose_depth_0_terminal_nodes_exist(self) -> None:
        """At depth=0 terminals are created for expose-based interfaces."""
        diag = build_viz_diagram(self._expose_system(), depth=0)
        ids = _node_ids(diag.peripheral_nodes)
        assert "terminal.req.OrderRequest" in ids
        assert "terminal.prov.OrderConfirmation" in ids

    def test_expose_depth_0_root_has_expose_ports(self) -> None:
        """At depth=0 the root boundary receives ports for each expose-based interface."""
        diag = build_viz_diagram(self._expose_system(), depth=0)
        port_names = {p.interface_name for p in diag.root.ports}
        assert "OrderRequest" in port_names
        assert "OrderConfirmation" in port_names

    def test_expose_depth_0_terminal_edges_connect_to_root_ports(self) -> None:
        """At depth=0 expose-terminal edges link terminal nodes to root boundary ports."""
        diag = build_viz_diagram(self._expose_system(), depth=0)
        assert len(diag.edges) == 2
        all_ports = collect_all_ports(diag)
        for edge in diag.edges:
            assert edge.source_port_id in all_ports
            assert edge.target_port_id in all_ports

    def test_expose_depth_1_terminal_edges_connect_to_child_ports(self) -> None:
        """At depth=1 expose-terminal edges connect directly to the child VizNode's port."""
        diag = build_viz_diagram(self._expose_system(), depth=1)
        all_ports = collect_all_ports(diag)
        # Edge for OrderRequest: terminal → Order__A.req.OrderRequest
        req_edge = next(e for e in diag.edges if e.interface_name == "OrderRequest")
        tgt = all_ports[req_edge.target_port_id]
        assert tgt.node_id == "Order__A"

    def test_expose_depth_2_expanded_child_terminal_edge_reaches_inner_node(self) -> None:
        """At depth=2, when A is expanded, the expose-terminal edge reaches SubA1 inside A."""
        sub_a1 = Component(name="SubA1", requires=[_iref("OrderRequest")])
        sub_a2 = Component(name="SubA2", provides=[_iref("Simple")])
        a = Component(
            name="A",
            components=[sub_a1, sub_a2],
            exposes=[ExposeDef(entity="SubA1", port="OrderRequest")],
        )
        b = Component(name="B", requires=[_iref("Simple")], provides=[_iref("OrderConfirmation")])
        order = System(
            name="Order",
            components=[a, b],
            exposes=[ExposeDef(entity="A", port="OrderRequest"), ExposeDef(entity="B", port="OrderConfirmation")],
        )
        diag = build_viz_diagram(order, depth=2)
        all_ports = collect_all_ports(diag)
        # A should be expanded as a VizBoundary.
        a_child = next(c for c in diag.root.children if c.label == "A")
        assert isinstance(a_child, VizBoundary)
        # The expose chain is followed to the lowest visible node: SubA1 inside A.
        req_edge = next(e for e in diag.edges if e.interface_name == "OrderRequest")
        tgt = all_ports[req_edge.target_port_id]
        assert "SubA1" in tgt.node_id


# ###############
# build_viz_diagram_all — depth parameter
# ###############


class TestBuildVizDiagramAllDepth:
    """Tests for the depth parameter of build_viz_diagram_all."""

    def _nested_arch_file(self) -> "ArchFile":
        """Return an ArchFile with a two-level system: Order → [A, B]."""
        comp_a = Component(name="A", requires=[_iref("OrderRequest")])
        comp_b = Component(name="B", provides=[_iref("OrderRequest")])
        order = System(name="Order", components=[comp_a, comp_b])
        return _arch_file(systems=[order])

    def test_depth_0_top_level_entities_are_opaque(self) -> None:
        """depth=0 shows top-level entities as opaque VizNodes."""
        af = self._nested_arch_file()
        diag = build_viz_diagram_all({"f": af}, depth=0)
        child = next(c for c in diag.root.children if c.label == "Order")
        assert isinstance(child, VizNode)

    def test_depth_1_top_level_entities_expanded(self) -> None:
        """depth=1 expands top-level entities that have children."""
        af = self._nested_arch_file()
        diag = build_viz_diagram_all({"f": af}, depth=1)
        child = next(c for c in diag.root.children if c.label == "Order")
        assert isinstance(child, VizBoundary)

    def test_depth_1_children_are_opaque(self) -> None:
        """depth=1 keeps the children of expanded top-level entities opaque."""
        af = self._nested_arch_file()
        diag = build_viz_diagram_all({"f": af}, depth=1)
        order_boundary = next(c for c in diag.root.children if isinstance(c, VizBoundary) and c.label == "Order")
        for grandchild in order_boundary.children:
            assert isinstance(grandchild, VizNode)

    def test_depth_2_top_level_entities_expanded(self) -> None:
        """depth=2 expands top-level entities that have children."""
        af = self._nested_arch_file()
        diag = build_viz_diagram_all({"f": af}, depth=2)
        child = next(c for c in diag.root.children if c.label == "Order")
        assert isinstance(child, VizBoundary)

    def test_depth_0_connections_are_present(self) -> None:
        """depth=0 produces edges connecting opaque entities via a channel."""
        sink = System(name="Sink", is_external=True, requires=[_iref("OrderRequest")])
        source = System(name="Source", is_external=True, provides=[_iref("OrderRequest")])
        conn = ConnectDef(
            src_entity="Source",
            src_port="OrderRequest",
            channel="ch",
            dst_entity="Sink",
            dst_port="OrderRequest",
        )
        af = _arch_file(systems=[source, sink], connects=[conn])
        diag = build_viz_diagram_all({"f": af}, depth=0)
        assert len(diag.edges) == 2  # source→channel and channel→sink

    def test_depth_1_external_entities_not_inside_expanded_system(self) -> None:
        """depth=1: external systems are siblings of Order, not inside it."""
        comp_a = Component(name="A", requires=[_iref("Req")])
        order = System(
            name="Order",
            components=[comp_a],
            exposes=[ExposeDef(entity="A", port="Req")],
        )
        ext = System(name="External", is_external=True, provides=[_iref("Req")])
        conn = ConnectDef(
            src_entity="External",
            src_port="Req",
            channel="ch",
            dst_entity="Order",
            dst_port="Req",
        )
        af = _arch_file(systems=[order, ext], connects=[conn])
        diag = build_viz_diagram_all({"f": af}, depth=1)
        order_boundary = next(c for c in diag.root.children if isinstance(c, VizBoundary) and c.label == "Order")
        child_labels = {c.label for c in order_boundary.children}
        assert "External" not in child_labels

    def test_depth_1_edges_connect_to_lowest_visible_node(self) -> None:
        """depth=1: edges from outside connect to the deepest visible node inside Order."""
        comp_a = Component(name="A", requires=[_iref("Req")])
        order = System(
            name="Order",
            components=[comp_a],
            exposes=[ExposeDef(entity="A", port="Req")],
        )
        ext = System(name="External", is_external=True, provides=[_iref("Req")])
        conn = ConnectDef(
            src_entity="External",
            src_port="Req",
            channel="ch",
            dst_entity="Order",
            dst_port="Req",
        )
        af = _arch_file(systems=[order, ext], connects=[conn])
        diag = build_viz_diagram_all({"f": af}, depth=1)
        order_boundary = next(c for c in diag.root.children if isinstance(c, VizBoundary) and c.label == "Order")
        # At depth=1, A is visible as an opaque VizNode inside Order.
        # The edge must connect to A's port (the lowest visible node), not Order's boundary port.
        inner_a = next(c for c in order_boundary.children if c.label == "A")
        inner_port_ids = {p.id for p in inner_a.ports}
        all_edges = diag.edges
        assert any(e.target_port_id in inner_port_ids for e in all_edges)

    def test_depth_none_default_matches_full_expansion(self) -> None:
        """depth=None (default) produces the same diagram as calling without depth."""
        af = self._nested_arch_file()
        diag_default = build_viz_diagram_all({"f": af})
        diag_none = build_viz_diagram_all({"f": af}, depth=None)
        types_default = {type(c) for c in diag_default.root.children}
        types_none = {type(c) for c in diag_none.root.children}
        assert types_default == types_none


# ###############
# build_viz_diagram_all
# ###############


def _arch_file(**kwargs: object) -> ArchFile:
    """Build a minimal ArchFile with the given fields."""
    defaults: dict[str, object] = {
        "imports": [],
        "enums": [],
        "types": [],
        "interfaces": [],
        "components": [],
        "systems": [],
        "users": [],
        "connects": [],
    }
    defaults.update(kwargs)
    return ArchFile(**defaults)  # type: ignore[arg-type]


class TestBuildVizDiagramAll:
    def test_empty_files_produces_empty_diagram(self) -> None:
        """An empty set of arch files produces a diagram with no children or edges."""
        diag = build_viz_diagram_all({})
        assert diag.root.label == "Architecture"
        assert diag.root.children == []
        assert diag.edges == []

    def test_single_file_components_become_children(self) -> None:
        """Top-level components from a single file appear as child nodes."""
        af = _arch_file(components=[Component(name="Alpha"), Component(name="Beta")])
        diag = build_viz_diagram_all({"f": af})
        child_labels = [c.label for c in diag.root.children if isinstance(c, VizNode)]
        assert "Alpha" in child_labels
        assert "Beta" in child_labels

    def test_systems_and_users_become_children(self) -> None:
        """Top-level systems and users are included as child nodes."""
        customer = UserDef(name="Customer")
        af = _arch_file(
            systems=[System(name="Backend")],
            users=[customer],
        )
        diag = build_viz_diagram_all({"f": af})
        child_labels = {c.label for c in diag.root.children if isinstance(c, VizNode)}
        assert "Backend" in child_labels
        assert "Customer" in child_labels

    def test_multiple_files_all_entities_present(self) -> None:
        """Entities from multiple files are merged into a single diagram."""
        af1 = _arch_file(systems=[System(name="Frontend")])
        af2 = _arch_file(systems=[System(name="Backend")])
        diag = build_viz_diagram_all({"a": af1, "b": af2})
        child_labels = {c.label for c in diag.root.children if isinstance(c, VizNode)}
        assert "Frontend" in child_labels
        assert "Backend" in child_labels

    def test_top_level_connects_produce_edges_and_channel_nodes(self) -> None:
        """Top-level connect statements wire entities and create channel nodes."""
        frontend = System(name="Frontend", provides=[_iref("API")])
        backend = System(name="Backend", requires=[_iref("API")])
        conn = ConnectDef(
            src_entity="Frontend",
            src_port="API",
            channel="bus",
            dst_entity="Backend",
            dst_port="API",
        )
        af = _arch_file(systems=[frontend, backend], connects=[conn])
        diag = build_viz_diagram_all({"f": af})
        # Two edges: Frontend → channel, channel → Backend.
        assert len(diag.edges) == 2
        # Channel node is a child.
        channel_nodes = [c for c in diag.root.children if isinstance(c, VizNode) and c.kind == "channel"]
        assert len(channel_nodes) == 1
        assert channel_nodes[0].label == "bus"

    def test_diagram_id_and_title(self) -> None:
        """The all-diagram uses 'Architecture' as title."""
        diag = build_viz_diagram_all({})
        assert diag.id == "diagram.all"
        assert diag.title == "Architecture"

    def test_no_peripheral_nodes(self) -> None:
        """The all-diagram has no peripheral terminal nodes (no owns interface)."""
        af = _arch_file(components=[Component(name="X", provides=[_iref("Data")])])
        diag = build_viz_diagram_all({"f": af})
        assert diag.peripheral_nodes == []

    def test_connects_across_files(self) -> None:
        """Top-level connects in different files are all included."""
        af1 = _arch_file(
            systems=[System(name="A", provides=[_iref("Msg")])],
            connects=[ConnectDef(src_entity="A", src_port="Msg", channel="ch1")],
        )
        af2 = _arch_file(
            systems=[System(name="B", requires=[_iref("Msg")])],
            connects=[ConnectDef(channel="ch1", dst_entity="B", dst_port="Msg")],
        )
        diag = build_viz_diagram_all({"a": af1, "b": af2})
        assert len(diag.edges) == 2


# ###############
# build_viz_diagram_all — expose-aware expansion
# ###############


def _expose(entity: str, port: str, as_name: str | None = None) -> ExposeDef:
    return ExposeDef(entity=entity, port=port, as_name=as_name)


class TestBuildVizDiagramAllExpanded:
    """Tests for expanded boundaries and expose-aware port resolution in build_viz_diagram_all."""

    def test_non_external_system_with_children_is_expanded_as_boundary(self) -> None:
        """A non-external System with inner components becomes a VizBoundary, not a VizNode."""
        inner = Component(name="Inner", provides=[_iref("X")])
        order = System(name="Order", components=[inner])
        af = _arch_file(systems=[order])
        diag = build_viz_diagram_all({"f": af})
        boundary_labels = {c.label for c in diag.root.children if isinstance(c, VizBoundary)}
        assert "Order" in boundary_labels

    def test_external_system_with_children_stays_as_opaque_node(self) -> None:
        """An external System is always rendered as an opaque VizNode, even with inner children."""
        inner = Component(name="Inner", provides=[_iref("X")])
        ext_sys = System(name="ExtSys", is_external=True, components=[inner])
        af = _arch_file(systems=[ext_sys])
        diag = build_viz_diagram_all({"f": af})
        node_labels = {c.label for c in diag.root.children if isinstance(c, VizNode)}
        assert "ExtSys" in node_labels
        boundary_labels = {c.label for c in diag.root.children if isinstance(c, VizBoundary)}
        assert "ExtSys" not in boundary_labels

    def test_leaf_system_without_children_stays_as_opaque_node(self) -> None:
        """A System with no inner structure stays as a VizNode in the all-diagram."""
        leaf = System(name="Leaf", provides=[_iref("X")])
        af = _arch_file(systems=[leaf])
        diag = build_viz_diagram_all({"f": af})
        node_labels = {c.label for c in diag.root.children if isinstance(c, VizNode)}
        assert "Leaf" in node_labels

    def test_user_def_stays_as_opaque_node(self) -> None:
        """UserDef at the top level is never expanded."""
        customer = UserDef(name="Customer")
        af = _arch_file(users=[customer])
        diag = build_viz_diagram_all({"f": af})
        node_labels = {c.label for c in diag.root.children if isinstance(c, VizNode)}
        assert "Customer" in node_labels

    def test_expanded_boundary_contains_inner_child_nodes(self) -> None:
        """Inner components of an expanded system appear as VizNode children of its boundary."""
        comp_a = Component(name="A", requires=[_iref("OrderRequest")])
        order = System(name="Order", components=[comp_a])
        af = _arch_file(systems=[order])
        diag = build_viz_diagram_all({"f": af})
        order_boundary = next(c for c in diag.root.children if isinstance(c, VizBoundary) and c.label == "Order")
        inner_labels = {c.label for c in order_boundary.children if isinstance(c, VizNode)}
        assert "A" in inner_labels

    def test_inner_connects_of_expanded_entity_appear_in_all_diagram(self) -> None:
        """Connect statements inside an expanded system produce edges in the all-diagram."""
        comp_a = Component(name="A", provides=[_iref("IFace")])
        comp_b = Component(name="B", requires=[_iref("IFace")])
        order = System(
            name="Order",
            components=[comp_a, comp_b],
            connects=[
                ConnectDef(src_entity="A", src_port="IFace", channel="inner_ch", dst_entity="B", dst_port="IFace")
            ],
        )
        af = _arch_file(systems=[order])
        diag = build_viz_diagram_all({"f": af})
        # Two edges: A → inner_ch, inner_ch → B
        assert len(diag.edges) == 2

    def test_exposed_port_connect_routes_edge_to_inner_node(self) -> None:
        """A top-level connect to Order.OrderRequest follows the expose chain to A inside Order."""
        comp_a = Component(name="A", requires=[_iref("OrderRequest")])
        order = System(
            name="Order",
            components=[comp_a],
            exposes=[_expose("A", "OrderRequest")],
        )
        ingestor = Component(name="DataIngestor", provides=[_iref("OrderRequest")])
        conn = ConnectDef(
            src_entity="DataIngestor",
            src_port="OrderRequest",
            channel="order_ch",
            dst_entity="Order",
            dst_port="OrderRequest",
        )
        af = _arch_file(systems=[order], components=[ingestor], connects=[conn])
        diag = build_viz_diagram_all({"f": af})
        assert len(diag.edges) == 2
        all_ports = collect_all_ports(diag)
        for edge in diag.edges:
            assert edge.source_port_id in all_ports
            assert edge.target_port_id in all_ports
        # The expose chain is followed to the lowest visible node: A inside Order.
        edge_ch_to_dst = diag.edges[1]
        dst_port = all_ports[edge_ch_to_dst.target_port_id]
        assert dst_port.node_id == "Order__A"

    def test_exposed_provides_port_routes_edge_from_inner_node(self) -> None:
        """A top-level connect from Order.OrderConfirmation follows the expose chain to B inside Order."""
        comp_b = Component(name="B", provides=[_iref("OrderConfirmation")])
        order = System(
            name="Order",
            components=[comp_b],
            exposes=[_expose("B", "OrderConfirmation")],
        )
        sink = Component(name="DataSink", requires=[_iref("OrderConfirmation")])
        conn = ConnectDef(
            src_entity="Order",
            src_port="OrderConfirmation",
            channel="conf_ch",
            dst_entity="DataSink",
            dst_port="OrderConfirmation",
        )
        af = _arch_file(systems=[order], components=[sink], connects=[conn])
        diag = build_viz_diagram_all({"f": af})
        assert len(diag.edges) == 2
        all_ports = collect_all_ports(diag)
        for edge in diag.edges:
            assert edge.source_port_id in all_ports
            assert edge.target_port_id in all_ports
        # The expose chain is followed to the lowest visible node: B inside Order.
        edge_src_to_ch = diag.edges[0]
        src_port = all_ports[edge_src_to_ch.source_port_id]
        assert src_port.node_id == "Order__B"

    def test_exposed_port_with_as_name_resolves_correctly(self) -> None:
        """expose A.OrderRequest as ExposedPort is reachable via the alias in a top-level connect."""
        comp_a = Component(name="A", requires=[_iref("OrderRequest")])
        order = System(
            name="Order",
            components=[comp_a],
            exposes=[_expose("A", "OrderRequest", as_name="ExposedPort")],
        )
        ingestor = Component(name="DataIngestor", provides=[_iref("OrderRequest")])
        conn = ConnectDef(
            src_entity="DataIngestor",
            src_port="OrderRequest",
            channel="ch",
            dst_entity="Order",
            dst_port="ExposedPort",
        )
        af = _arch_file(systems=[order], components=[ingestor], connects=[conn])
        diag = build_viz_diagram_all({"f": af})
        assert len(diag.edges) == 2
        all_ports = collect_all_ports(diag)
        edge_ch_to_dst = diag.edges[1]
        dst_port = all_ports[edge_ch_to_dst.target_port_id]
        assert dst_port.node_id == "Order__A"

    def test_unexposed_port_on_expanded_system_produces_no_channel_to_dst_edge(self) -> None:
        """When a port has no matching expose, the channel→dst edge is not produced.

        The src→channel edge is still produced because DataIngestor (opaque) resolves.
        """
        comp_a = Component(name="A", requires=[_iref("OrderRequest")])
        order = System(name="Order", components=[comp_a])  # no exposes
        ingestor = Component(name="DataIngestor", provides=[_iref("OrderRequest")])
        conn = ConnectDef(
            src_entity="DataIngestor",
            src_port="OrderRequest",
            channel="ch",
            dst_entity="Order",
            dst_port="OrderRequest",
        )
        af = _arch_file(systems=[order], components=[ingestor], connects=[conn])
        diag = build_viz_diagram_all({"f": af})
        # Only the src→channel edge is produced; channel→Order fails (no expose).
        assert len(diag.edges) == 1
        assert "DataIngestor" in diag.edges[0].source_port_id

    def test_all_ports_resolvable_with_expanded_entities(self) -> None:
        """collect_all_ports covers all port IDs referenced by edges in the all-diagram."""
        comp_a = Component(name="A", requires=[_iref("OrderRequest")])
        order = System(
            name="Order",
            components=[comp_a],
            exposes=[_expose("A", "OrderRequest")],
        )
        ingestor = Component(name="DataIngestor", provides=[_iref("OrderRequest")])
        conn = ConnectDef(
            src_entity="DataIngestor",
            src_port="OrderRequest",
            channel="ch",
            dst_entity="Order",
            dst_port="OrderRequest",
        )
        af = _arch_file(systems=[order], components=[ingestor], connects=[conn])
        diag = build_viz_diagram_all({"f": af})
        all_ports = collect_all_ports(diag)
        for edge in diag.edges:
            assert edge.source_port_id in all_ports, f"missing src port {edge.source_port_id}"
            assert edge.target_port_id in all_ports, f"missing dst port {edge.target_port_id}"

    def test_full_pipeline_with_two_exposed_ports_and_inner_connect(self) -> None:
        """Integration test matching the user's Order system example.

        DataIngestor → $order_request → A (via Order.expose A.OrderRequest)
        A → $mychannel → B (inner connect)
        B → $order_confirmation → DataSink (via Order.expose B.OrderConfirmation)
        """
        comp_a = Component(name="A", requires=[_iref("OrderRequest")], provides=[_iref("Simple")])
        comp_b = Component(name="B", requires=[_iref("Simple")], provides=[_iref("OrderConfirmation")])
        order = System(
            name="Order",
            components=[comp_a, comp_b],
            connects=[
                ConnectDef(src_entity="A", src_port="Simple", channel="mychannel", dst_entity="B", dst_port="Simple")
            ],
            exposes=[_expose("A", "OrderRequest"), _expose("B", "OrderConfirmation")],
        )
        ingestor = System(name="DataIngestor", is_external=True, provides=[_iref("OrderRequest")])
        sink = System(name="DataSink", is_external=True, requires=[_iref("OrderConfirmation")])
        top_connects = [
            ConnectDef(
                src_entity="DataIngestor",
                src_port="OrderRequest",
                channel="order_request",
                dst_entity="Order",
                dst_port="OrderRequest",
            ),
            ConnectDef(
                src_entity="Order",
                src_port="OrderConfirmation",
                channel="order_confirmation",
                dst_entity="DataSink",
                dst_port="OrderConfirmation",
            ),
        ]
        af = _arch_file(systems=[order, ingestor, sink], connects=top_connects)
        diag = build_viz_diagram_all({"f": af})

        # Order is expanded; DataIngestor and DataSink are external opaque nodes.
        child_labels = {c.label for c in diag.root.children}
        assert "Order" in child_labels
        assert "DataIngestor" in child_labels
        assert "DataSink" in child_labels
        order_boundary = next(c for c in diag.root.children if isinstance(c, VizBoundary) and c.label == "Order")
        inner_labels = {c.label for c in order_boundary.children if isinstance(c, VizNode)}
        assert "A" in inner_labels
        assert "B" in inner_labels

        # Inner connect A→mychannel→B: 2 edges.
        # Top-level connects via expose: 4 edges (2 per channel connect).
        # Total: 6 edges.
        assert len(diag.edges) == 6

        # All port IDs are resolvable.
        all_ports = collect_all_ports(diag)
        for edge in diag.edges:
            assert edge.source_port_id in all_ports, f"missing src port {edge.source_port_id}"
            assert edge.target_port_id in all_ports, f"missing dst port {edge.target_port_id}"

        # The edge from order_request channel to dst routes to A (inner node via expose chain).
        ch_to_order_edges = [e for e in diag.edges if "order_request" in e.source_port_id]
        assert len(ch_to_order_edges) == 1
        dst_port = all_ports[ch_to_order_edges[0].target_port_id]
        assert dst_port.node_id == "Order__A"

        # The edge from src to order_confirmation channel comes from B (inner node via expose chain).
        order_to_ch_edges = [e for e in diag.edges if "order_confirmation" in e.target_port_id]
        assert len(order_to_ch_edges) == 1
        src_port = all_ports[order_to_ch_edges[0].source_port_id]
        assert src_port.node_id == "Order__B"


# ###############
# build_viz_diagram — depth + connection correctness
# ###############


class TestDepthConnectionEdges:
    """Tests that connect edges are produced with correct port IDs at each depth level.

    Structural expansion tests (VizBoundary vs VizNode) live in
    TestBuildVizDiagramDepth.  This class focuses exclusively on *which edges*
    appear and *which nodes they connect* at depths 0, 1, 2, and None.
    """

    def _two_child_system(self) -> System:
        """Root → A (provides Out) and B (requires Out), connected via $ch."""
        a = Component(name="A", provides=[_iref("Out")])
        b = Component(name="B", requires=[_iref("Out")])
        return System(
            name="Root",
            components=[a, b],
            connects=[_connect("A", "Out", "B", "Out", channel="ch")],
        )

    # depth=0 — connects not rendered because children are absent ----------

    def test_depth_0_internal_connect_produces_no_edges(self) -> None:
        """At depth=0 no children exist, so internal connects yield no edges."""
        diag = build_viz_diagram(self._two_child_system(), depth=0)
        assert diag.edges == []

    # depth=1 — children are opaque VizNodes, connects ARE rendered ----------

    def test_depth_1_channel_connect_produces_two_edges(self) -> None:
        """At depth=1 a channel connect (A→$ch→B) produces exactly two edges."""
        diag = build_viz_diagram(self._two_child_system(), depth=1)
        assert len(diag.edges) == 2

    def test_depth_1_first_edge_source_is_child_a(self) -> None:
        """At depth=1, edges[0] source port belongs to child A (provider)."""
        diag = build_viz_diagram(self._two_child_system(), depth=1)
        all_ports = collect_all_ports(diag)
        src_port = all_ports[diag.edges[0].source_port_id]
        assert src_port.node_id == "Root__A"
        assert src_port.direction == "provides"

    def test_depth_1_second_edge_target_is_child_b(self) -> None:
        """At depth=1, edges[1] target port belongs to child B (requirer)."""
        diag = build_viz_diagram(self._two_child_system(), depth=1)
        all_ports = collect_all_ports(diag)
        tgt_port = all_ports[diag.edges[1].target_port_id]
        assert tgt_port.node_id == "Root__B"
        assert tgt_port.direction == "requires"

    def test_depth_1_all_edge_ports_resolvable(self) -> None:
        """At depth=1, every edge port ID resolves in collect_all_ports."""
        diag = build_viz_diagram(self._two_child_system(), depth=1)
        all_ports = collect_all_ports(diag)
        for edge in diag.edges:
            assert edge.source_port_id in all_ports, f"missing src {edge.source_port_id}"
            assert edge.target_port_id in all_ports, f"missing dst {edge.target_port_id}"

    def test_depth_1_channel_node_is_intermediate(self) -> None:
        """At depth=1, a channel VizNode sits between the two child nodes."""
        diag = build_viz_diagram(self._two_child_system(), depth=1)
        all_ports = collect_all_ports(diag)
        channel_nodes = [c for c in diag.root.children if isinstance(c, VizNode) and c.kind == "channel"]
        assert len(channel_nodes) == 1
        ch = channel_nodes[0]
        # edges[0] target is the channel; edges[1] source is the channel
        assert all_ports[diag.edges[0].target_port_id].node_id == ch.id
        assert all_ports[diag.edges[1].source_port_id].node_id == ch.id

    def test_depth_1_channel_produces_two_edges(self) -> None:
        """A channel connect at depth=1 produces exactly two edges."""
        a = Component(name="A", provides=[_iref("X")])
        b = Component(name="B", requires=[_iref("X")])
        sys = System(
            name="Root",
            components=[a, b],
            connects=[_connect("A", "X", "B", "X", channel="ch")],
        )
        diag = build_viz_diagram(sys, depth=1)
        assert len(diag.edges) == 2

    def test_depth_1_channel_connect_src_dst_nodes(self) -> None:
        """A channel connect at depth=1 produces two edges linking the correct node IDs."""
        a = Component(name="A", provides=[_iref("X")])
        b = Component(name="B", requires=[_iref("X")])
        sys = System(
            name="Root",
            components=[a, b],
            connects=[_connect("A", "X", "B", "X", channel="ch")],
        )
        diag = build_viz_diagram(sys, depth=1)
        assert len(diag.edges) == 2
        all_ports = collect_all_ports(diag)
        src_node_ids = {all_ports[e.source_port_id].node_id for e in diag.edges}
        dst_node_ids = {all_ports[e.target_port_id].node_id for e in diag.edges}
        assert "Root__A" in src_node_ids
        assert "Root__B" in dst_node_ids

    def test_depth_1_multiple_connects_produce_correct_edge_count(self) -> None:
        """Two channel connects at depth=1 produce four edges in total."""
        a = Component(name="A", requires=[_iref("X"), _iref("Y")])
        b = Component(name="B", provides=[_iref("X")])
        c = Component(name="C", provides=[_iref("Y")])
        sys = System(
            name="Root",
            components=[a, b, c],
            connects=[
                _connect("B", "X", "A", "X", channel="ch1"),
                _connect("C", "Y", "A", "Y", channel="ch2"),
            ],
        )
        diag = build_viz_diagram(sys, depth=1)
        assert len(diag.edges) == 4
        all_ports = collect_all_ports(diag)
        for edge in diag.edges:
            assert edge.source_port_id in all_ports
            assert edge.target_port_id in all_ports

    # depth=2 — grandchildren remain opaque; sub-system connects appear ------

    def _three_level_system(self) -> System:
        """Root → Sub (System) → A (provides Out) + B (requires Out), connected via $inner."""
        a = Component(name="A", provides=[_iref("Out")])
        b = Component(name="B", requires=[_iref("Out")])
        sub = System(
            name="Sub",
            components=[a, b],
            connects=[_connect("A", "Out", "B", "Out", channel="inner")],
        )
        return System(name="Root", systems=[sub])

    def test_depth_1_sub_system_opaque_no_inner_edges(self) -> None:
        """At depth=1, Sub is an opaque VizNode so its inner connects produce no edges."""
        diag = build_viz_diagram(self._three_level_system(), depth=1)
        assert diag.edges == []

    def test_depth_2_sub_system_expanded_inner_edges_appear(self) -> None:
        """At depth=2, Sub is expanded and its inner connect A→$inner→B is visible."""
        diag = build_viz_diagram(self._three_level_system(), depth=2)
        assert len(diag.edges) == 2

    def test_depth_2_inner_edge_ports_reference_grandchildren(self) -> None:
        """At depth=2, edge ports reference A and B inside the expanded Sub boundary."""
        diag = build_viz_diagram(self._three_level_system(), depth=2)
        all_ports = collect_all_ports(diag)
        for edge in diag.edges:
            assert edge.source_port_id in all_ports
            assert edge.target_port_id in all_ports
        src_port = all_ports[diag.edges[0].source_port_id]
        assert src_port.node_id == "Root__Sub__A"
        tgt_port = all_ports[diag.edges[1].target_port_id]
        assert tgt_port.node_id == "Root__Sub__B"

    # depth=3 vs depth=2 — four-level hierarchy controls when deepest edges appear

    def _four_level_system(self) -> System:
        """Root → Mid → Sub → A (provides Out) + B (requires Out), connected via $leaf."""
        a = Component(name="A", provides=[_iref("Out")])
        b = Component(name="B", requires=[_iref("Out")])
        sub = System(
            name="Sub",
            components=[a, b],
            connects=[_connect("A", "Out", "B", "Out", channel="leaf")],
        )
        mid = System(name="Mid", systems=[sub])
        return System(name="Root", systems=[mid])

    def test_depth_2_four_level_sub_opaque_no_leaf_edges(self) -> None:
        """At depth=2, Sub is still opaque (Mid expanded but Sub is not), so no edges."""
        diag = build_viz_diagram(self._four_level_system(), depth=2)
        assert diag.edges == []

    def test_depth_3_four_level_sub_expanded_leaf_edges_appear(self) -> None:
        """At depth=3, Sub is expanded and the leaf connect A→$leaf→B is visible."""
        diag = build_viz_diagram(self._four_level_system(), depth=3)
        assert len(diag.edges) == 2

    def test_depth_3_leaf_edge_ports_reference_deepest_nodes(self) -> None:
        """At depth=3, edge ports carry the full four-level path for A and B."""
        diag = build_viz_diagram(self._four_level_system(), depth=3)
        all_ports = collect_all_ports(diag)
        for edge in diag.edges:
            assert edge.source_port_id in all_ports
            assert edge.target_port_id in all_ports
        src_port = all_ports[diag.edges[0].source_port_id]
        assert src_port.node_id == "Root__Mid__Sub__A"
        tgt_port = all_ports[diag.edges[1].target_port_id]
        assert tgt_port.node_id == "Root__Mid__Sub__B"

    def test_depth_none_four_level_shows_all_edges(self) -> None:
        """depth=None (full expansion) shows the leaf-level connect edges."""
        diag = build_viz_diagram(self._four_level_system())
        assert len(diag.edges) == 2
        all_ports = collect_all_ports(diag)
        for edge in diag.edges:
            assert edge.source_port_id in all_ports
            assert edge.target_port_id in all_ports


# ###############
# build_viz_diagram_all — depth + connection correctness
# ###############


class TestBuildVizDiagramAllDepthConnections:
    """Tests that build_viz_diagram_all produces the right edges at each depth.

    Focuses on which edges appear and where their ports land as depth controls
    which systems are expanded vs. opaque.
    """

    def _single_pipeline(self) -> dict[str, ArchFile]:
        """Pipeline (System) → A (provides Out) + B (requires Out), connected via $ab."""
        a = Component(name="A", provides=[_iref("Out")])
        b = Component(name="B", requires=[_iref("Out")])
        pipeline = System(
            name="Pipeline",
            components=[a, b],
            connects=[_connect("A", "Out", "B", "Out", channel="ab")],
        )
        return {"f": _arch_file(systems=[pipeline])}

    def test_depth_0_top_level_opaque_no_inner_edges(self) -> None:
        """depth=0: Pipeline is opaque — its inner connect produces no edges."""
        diag = build_viz_diagram_all(self._single_pipeline(), depth=0)
        assert diag.edges == []

    def test_depth_1_top_level_expanded_inner_edges_visible(self) -> None:
        """depth=1: Pipeline is expanded — inner connect A→$ab→B produces two edges."""
        diag = build_viz_diagram_all(self._single_pipeline(), depth=1)
        assert len(diag.edges) == 2

    def test_depth_1_inner_edge_ports_reference_child_nodes(self) -> None:
        """depth=1: edge ports of the inner connect reference A and B inside Pipeline."""
        diag = build_viz_diagram_all(self._single_pipeline(), depth=1)
        all_ports = collect_all_ports(diag)
        for edge in diag.edges:
            assert edge.source_port_id in all_ports
            assert edge.target_port_id in all_ports
        src_port = all_ports[diag.edges[0].source_port_id]
        assert src_port.node_id == "Pipeline__A"
        tgt_port = all_ports[diag.edges[1].target_port_id]
        assert tgt_port.node_id == "Pipeline__B"

    def _nested_pipeline(self) -> dict[str, ArchFile]:
        """Outer (System) → Inner (System) → A (provides Out) + B (requires Out), connected via $ab."""
        a = Component(name="A", provides=[_iref("Out")])
        b = Component(name="B", requires=[_iref("Out")])
        inner = System(
            name="Inner",
            components=[a, b],
            connects=[_connect("A", "Out", "B", "Out", channel="ab")],
        )
        outer = System(name="Outer", systems=[inner])
        return {"f": _arch_file(systems=[outer])}

    def test_depth_1_outer_expanded_inner_opaque_no_leaf_edges(self) -> None:
        """depth=1: Outer expanded, Inner still opaque — leaf connect not visible."""
        diag = build_viz_diagram_all(self._nested_pipeline(), depth=1)
        assert diag.edges == []

    def test_depth_2_both_expanded_leaf_edges_visible(self) -> None:
        """depth=2: Outer and Inner both expanded — inner connect produces two edges."""
        diag = build_viz_diagram_all(self._nested_pipeline(), depth=2)
        assert len(diag.edges) == 2

    def test_depth_2_leaf_edge_ports_reference_deepest_nodes(self) -> None:
        """depth=2: edge ports carry the full path Outer__Inner__A and Outer__Inner__B."""
        diag = build_viz_diagram_all(self._nested_pipeline(), depth=2)
        all_ports = collect_all_ports(diag)
        for edge in diag.edges:
            assert edge.source_port_id in all_ports
            assert edge.target_port_id in all_ports
        src_port = all_ports[diag.edges[0].source_port_id]
        assert src_port.node_id == "Outer__Inner__A"
        tgt_port = all_ports[diag.edges[1].target_port_id]
        assert tgt_port.node_id == "Outer__Inner__B"

    def test_depth_none_nested_pipeline_shows_all_edges(self) -> None:
        """depth=None (default): all levels expanded, leaf connect always visible."""
        diag = build_viz_diagram_all(self._nested_pipeline())
        assert len(diag.edges) == 2
        all_ports = collect_all_ports(diag)
        for edge in diag.edges:
            assert edge.source_port_id in all_ports
            assert edge.target_port_id in all_ports

    def test_depth_1_top_level_connect_edges_still_present_with_opaque_entities(self) -> None:
        """depth=1: top-level connects between opaque external entities produce edges."""
        src = System(name="Src", is_external=True, provides=[_iref("Msg")])
        dst = System(name="Dst", is_external=True, requires=[_iref("Msg")])
        conn = _connect("Src", "Msg", "Dst", "Msg", channel="bus")
        af = _arch_file(systems=[src, dst], connects=[conn])
        diag = build_viz_diagram_all({"f": af}, depth=1)
        # Two external entities + channel connect → 2 edges
        assert len(diag.edges) == 2
        all_ports = collect_all_ports(diag)
        for edge in diag.edges:
            assert edge.source_port_id in all_ports
            assert edge.target_port_id in all_ports

    def test_depth_2_channel_connect_two_edges(self) -> None:
        """depth=2: a channel connect inside a doubly-nested system yields two edges."""
        a = Component(name="A", provides=[_iref("X")])
        b = Component(name="B", requires=[_iref("X")])
        inner = System(
            name="Inner",
            components=[a, b],
            connects=[_connect("A", "X", "B", "X", channel="ch")],
        )
        outer = System(name="Outer", systems=[inner])
        af = _arch_file(systems=[outer])
        diag = build_viz_diagram_all({"f": af}, depth=2)
        assert len(diag.edges) == 2
        all_ports = collect_all_ports(diag)
        src_node_ids = {all_ports[e.source_port_id].node_id for e in diag.edges}
        dst_node_ids = {all_ports[e.target_port_id].node_id for e in diag.edges}
        assert "Outer__Inner__A" in src_node_ids
        assert "Outer__Inner__B" in dst_node_ids
