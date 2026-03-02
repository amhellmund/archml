# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the abstract visualization topology model and its builder."""

from archml.model.entities import Component, Connection, ConnectionEndpoint, InterfaceRef, System
from archml.views.topology import (
    VizBoundary,
    VizNode,
    VizPort,
    build_viz_diagram,
    collect_all_ports,
)

# ###############
# Helpers
# ###############


def _iref(name: str, version: str | None = None) -> InterfaceRef:
    return InterfaceRef(name=name, version=version)


def _conn(
    source: str,
    target: str,
    interface: str,
    version: str | None = None,
    protocol: str | None = None,
    is_async: bool = False,
    description: str | None = None,
) -> Connection:
    return Connection(
        source=ConnectionEndpoint(entity=source),
        target=ConnectionEndpoint(entity=target),
        interface=InterfaceRef(name=interface, version=version),
        protocol=protocol,
        is_async=is_async,
        description=description,
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


def test_root_boundary_label_and_title() -> None:
    """Root boundary label is the entity mnemonic; title is the human name."""
    comp = Component(name="order_service", title="Order Service")
    diag = build_viz_diagram(comp)
    assert diag.root.label == "order_service"
    assert diag.root.title == "Order Service"


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


def test_root_boundary_tags_propagated() -> None:
    comp = Component(name="C", tags=["critical", "pci"])
    diag = build_viz_diagram(comp)
    assert diag.root.tags == ["critical", "pci"]


# ###############
# VizDiagram — metadata
# ###############


def test_diagram_id_prefixed() -> None:
    comp = Component(name="Worker")
    diag = build_viz_diagram(comp)
    assert diag.id == "diagram.Worker"


def test_diagram_title_from_entity_title() -> None:
    comp = Component(name="w", title="Worker")
    diag = build_viz_diagram(comp)
    assert diag.title == "Worker"


def test_diagram_title_falls_back_to_name() -> None:
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


def test_child_node_description_and_tags() -> None:
    child = Component(name="C", description="desc", tags=["t1"])
    parent = System(name="S", components=[child])
    diag = build_viz_diagram(parent)
    node = next(n for n in diag.root.children if isinstance(n, VizNode))
    assert node.description == "desc"
    assert node.tags == ["t1"]


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


def test_terminal_port_direction_matches_interface_direction() -> None:
    """A requires terminal has a requires port; a provides terminal has a provides port."""
    comp = Component(name="C", requires=[_iref("In")], provides=[_iref("Out")])
    diag = build_viz_diagram(comp)
    by_id = {n.id: n for n in diag.peripheral_nodes}
    req_terminal = by_id["terminal.req.In"]
    prov_terminal = by_id["terminal.prov.Out"]
    assert req_terminal.ports[0].direction == "requires"
    assert prov_terminal.ports[0].direction == "provides"


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
# Peripheral nodes — external actors
# ###############


def test_external_actor_stub_created_for_unresolved_endpoint() -> None:
    """An endpoint not among the children creates a stub external node."""
    child = Component(name="A", requires=[_iref("IFace")])
    conn = _conn("A", "StripeAPI", "IFace")
    parent = System(name="S", components=[child], connections=[conn])
    diag = build_viz_diagram(parent)
    ext_ids = _node_ids(diag.peripheral_nodes)
    assert "ext.StripeAPI" in ext_ids


def test_external_actor_stub_has_external_kind() -> None:
    child = Component(name="A", requires=[_iref("IFace")])
    conn = _conn("A", "Ext", "IFace")
    parent = System(name="S", components=[child], connections=[conn])
    diag = build_viz_diagram(parent)
    ext_node = next(n for n in diag.peripheral_nodes if n.id == "ext.Ext")
    assert ext_node.kind in ("external_component", "external_system")


def test_external_actor_resolved_from_external_entities() -> None:
    """When external_entities provides model data it is used for the node."""
    child = Component(name="A", requires=[_iref("Pay")])
    stripe = Component(name="StripeAPI", title="Stripe", provides=[_iref("Pay")], is_external=True)
    conn = _conn("A", "StripeAPI", "Pay")
    parent = System(name="S", components=[child], connections=[conn])

    diag = build_viz_diagram(parent, external_entities={"StripeAPI": stripe})

    ext_node = next(n for n in diag.peripheral_nodes if n.label == "StripeAPI")
    assert ext_node.title == "Stripe"
    assert ext_node.kind == "external_component"
    # Resolved node carries full ports.
    assert any(p.interface_name == "Pay" for p in ext_node.ports)


def test_external_actor_appears_only_once_even_in_multiple_connections() -> None:
    """The same external actor referenced twice produces a single peripheral node."""
    a = Component(name="A", requires=[_iref("X"), _iref("Y")])
    conn1 = _conn("A", "Ext", "X")
    conn2 = _conn("A", "Ext", "Y")
    parent = System(name="S", components=[a], connections=[conn1, conn2])
    diag = build_viz_diagram(parent)
    ext_nodes = [n for n in diag.peripheral_nodes if n.label == "Ext"]
    assert len(ext_nodes) == 1


def test_child_not_added_to_peripheral_nodes() -> None:
    """A direct child of the focus entity never appears in peripheral_nodes."""
    child_a = Component(name="A", requires=[_iref("IFace")])
    child_b = Component(name="B", provides=[_iref("IFace")])
    conn = _conn("A", "B", "IFace")
    parent = System(name="S", components=[child_a, child_b], connections=[conn])
    diag = build_viz_diagram(parent)
    peripheral_labels = {n.label for n in diag.peripheral_nodes}
    assert "A" not in peripheral_labels
    assert "B" not in peripheral_labels


# ###############
# Edges
# ###############


def test_edge_created_for_connection() -> None:
    """A VizEdge is created for each connect statement."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    conn = _conn("A", "B", "IFace")
    parent = System(name="S", components=[a, b], connections=[conn])
    diag = build_viz_diagram(parent)
    assert len(diag.edges) == 1


def test_edge_label_is_interface_name() -> None:
    a = Component(name="A", requires=[_iref("PayReq")])
    b = Component(name="B", provides=[_iref("PayReq")])
    conn = _conn("A", "B", "PayReq")
    parent = System(name="S", components=[a, b], connections=[conn])
    diag = build_viz_diagram(parent)
    assert diag.edges[0].label == "PayReq"


def test_edge_label_includes_version() -> None:
    a = Component(name="A", requires=[_iref("API", "v2")])
    b = Component(name="B", provides=[_iref("API", "v2")])
    conn = _conn("A", "B", "API", version="v2")
    parent = System(name="S", components=[a, b], connections=[conn])
    diag = build_viz_diagram(parent)
    assert diag.edges[0].label == "API@v2"


def test_edge_source_port_is_requires_port() -> None:
    """Edge source_port_id references a requires port on the source node."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    conn = _conn("A", "B", "IFace")
    parent = System(name="S", components=[a, b], connections=[conn])
    diag = build_viz_diagram(parent)
    all_ports = collect_all_ports(diag)
    src_port = all_ports[diag.edges[0].source_port_id]
    assert src_port.direction == "requires"
    assert src_port.interface_name == "IFace"


def test_edge_target_port_is_provides_port() -> None:
    """Edge target_port_id references a provides port on the target node."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    conn = _conn("A", "B", "IFace")
    parent = System(name="S", components=[a, b], connections=[conn])
    diag = build_viz_diagram(parent)
    all_ports = collect_all_ports(diag)
    tgt_port = all_ports[diag.edges[0].target_port_id]
    assert tgt_port.direction == "provides"
    assert tgt_port.interface_name == "IFace"


def test_edge_source_and_target_port_owners() -> None:
    """Source port belongs to the source node; target port to the target node."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    conn = _conn("A", "B", "IFace")
    parent = System(name="S", components=[a, b], connections=[conn])
    diag = build_viz_diagram(parent)
    all_ports = collect_all_ports(diag)
    edge = diag.edges[0]
    assert all_ports[edge.source_port_id].node_id == "S__A"
    assert all_ports[edge.target_port_id].node_id == "S__B"


def test_edge_protocol_and_async_propagated() -> None:
    a = Component(name="A", requires=[_iref("X")])
    b = Component(name="B", provides=[_iref("X")])
    conn = _conn("A", "B", "X", protocol="gRPC", is_async=True, description="async call")
    parent = System(name="S", components=[a, b], connections=[conn])
    diag = build_viz_diagram(parent)
    edge = diag.edges[0]
    assert edge.protocol == "gRPC"
    assert edge.is_async is True
    assert edge.description == "async call"


def test_multiple_edges_created() -> None:
    a = Component(name="A", requires=[_iref("X"), _iref("Y")])
    b = Component(name="B", provides=[_iref("X")])
    c = Component(name="C", provides=[_iref("Y")])
    conns = [_conn("A", "B", "X"), _conn("A", "C", "Y")]
    parent = System(name="S", components=[a, b, c], connections=conns)
    diag = build_viz_diagram(parent)
    assert len(diag.edges) == 2


def test_edge_to_unknown_source_creates_stub_and_edge() -> None:
    """An unknown source endpoint becomes a stub external node and the edge is kept."""
    b = Component(name="B", provides=[_iref("IFace")])
    conn = _conn("Ghost", "B", "IFace")
    parent = System(name="S", components=[b], connections=[conn])
    diag = build_viz_diagram(parent)
    # Stub node is created for "Ghost".
    peripheral_labels = {n.label for n in diag.peripheral_nodes}
    assert "Ghost" in peripheral_labels
    # Edge is still produced (connecting stub → B).
    assert len(diag.edges) == 1


def test_edge_to_unknown_target_creates_stub_and_edge() -> None:
    """An unknown target endpoint becomes a stub external node and the edge is kept."""
    a = Component(name="A", requires=[_iref("IFace")])
    conn = _conn("A", "Ghost", "IFace")
    parent = System(name="S", components=[a], connections=[conn])
    diag = build_viz_diagram(parent)
    peripheral_labels = {n.label for n in diag.peripheral_nodes}
    assert "Ghost" in peripheral_labels
    assert len(diag.edges) == 1


# ###############
# Implicit ports
# ###############


def test_implicit_port_created_when_requires_missing() -> None:
    """When the source lacks an explicit requires declaration an implicit port is added."""
    # A has no requires declarations at all.
    a = Component(name="A")
    b = Component(name="B", provides=[_iref("IFace")])
    conn = _conn("A", "B", "IFace")
    parent = System(name="S", components=[a, b], connections=[conn])
    diag = build_viz_diagram(parent)

    assert len(diag.edges) == 1
    all_ports = collect_all_ports(diag)
    src_port = all_ports[diag.edges[0].source_port_id]
    assert src_port.direction == "requires"
    assert src_port.interface_name == "IFace"


def test_implicit_port_created_when_provides_missing() -> None:
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B")  # no provides
    conn = _conn("A", "B", "IFace")
    parent = System(name="S", components=[a, b], connections=[conn])
    diag = build_viz_diagram(parent)

    assert len(diag.edges) == 1
    all_ports = collect_all_ports(diag)
    tgt_port = all_ports[diag.edges[0].target_port_id]
    assert tgt_port.direction == "provides"
    assert tgt_port.interface_name == "IFace"


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


def test_collect_all_ports_includes_external_node_ports() -> None:
    child = Component(name="A", requires=[_iref("Pay")])
    stripe = Component(name="Stripe", provides=[_iref("Pay")], is_external=True)
    conn = _conn("A", "Stripe", "Pay")
    parent = System(name="S", components=[child], connections=[conn])
    diag = build_viz_diagram(parent, external_entities={"Stripe": stripe})
    all_ports = collect_all_ports(diag)
    prov_ports = [p for p in all_ports.values() if p.direction == "provides" and p.interface_name == "Pay"]
    assert len(prov_ports) >= 1


def test_collect_all_ports_returns_unique_ids() -> None:
    """All returned port IDs are distinct."""
    a = Component(name="A", requires=[_iref("X")])
    b = Component(name="B", provides=[_iref("X")])
    conn = _conn("A", "B", "X")
    parent = System(name="S", components=[a, b], connections=[conn])
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
        title="Order Service",
        requires=[_iref("PaymentRequest"), _iref("InventoryCheck")],
        provides=[_iref("OrderConfirmation")],
    )
    payment_gw = Component(
        name="PaymentGateway",
        title="Payment Gateway",
        tags=["critical", "pci-scope"],
        requires=[_iref("PaymentRequest")],
        provides=[_iref("PaymentResult")],
    )
    inventory = Component(
        name="InventoryManager",
        title="Inventory Manager",
        requires=[_iref("InventoryCheck")],
        provides=[_iref("InventoryStatus")],
    )
    stripe = Component(
        name="StripeAPI",
        title="Stripe Payment API",
        requires=[_iref("PaymentRequest")],
        provides=[_iref("PaymentResult")],
        is_external=True,
    )

    ecommerce = System(
        name="ECommerce",
        title="E-Commerce Platform",
        components=[order_svc, payment_gw, inventory],
        connections=[
            _conn("OrderService", "PaymentGateway", "PaymentRequest"),
            _conn("OrderService", "InventoryManager", "InventoryCheck"),
            _conn("PaymentGateway", "StripeAPI", "PaymentRequest", protocol="HTTP", is_async=True),
        ],
    )

    diag = build_viz_diagram(ecommerce, external_entities={"StripeAPI": stripe})

    # Root boundary is ECommerce.
    assert diag.root.id == "ECommerce"
    assert diag.root.kind == "system"

    # Three children inside the boundary.
    child_labels = {c.label for c in diag.root.children if isinstance(c, VizNode)}
    assert child_labels == {"OrderService", "PaymentGateway", "InventoryManager"}

    # StripeAPI is a peripheral (external) node.
    peripheral_labels = {n.label for n in diag.peripheral_nodes}
    assert "StripeAPI" in peripheral_labels
    stripe_node = next(n for n in diag.peripheral_nodes if n.label == "StripeAPI")
    assert stripe_node.kind == "external_component"

    # Three edges.
    assert len(diag.edges) == 3
    edge_labels = {e.label for e in diag.edges}
    assert "PaymentRequest" in edge_labels
    assert "InventoryCheck" in edge_labels

    # Async annotation on the Stripe edge.
    stripe_edge = next(e for e in diag.edges if e.protocol == "HTTP")
    assert stripe_edge.is_async is True

    # All ports resolvable.
    all_ports = collect_all_ports(diag)
    for edge in diag.edges:
        assert edge.source_port_id in all_ports
        assert edge.target_port_id in all_ports
