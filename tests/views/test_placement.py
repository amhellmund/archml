# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Sugiyama-style placement algorithm."""

import pytest

from archml.model.entities import Component, Connection, ConnectionEndpoint, InterfaceRef, System
from archml.views.placement import (
    LayoutConfig,
    LayoutPlan,
    compute_layout,
)
from archml.views.topology import (
    VizBoundary,
    VizDiagram,
    VizEdge,
    VizNode,
    VizPort,
    build_viz_diagram,
)

# ###############
# Helpers
# ###############


def _iref(name: str, version: str | None = None) -> InterfaceRef:
    return InterfaceRef(name=name, version=version)


def _conn(source: str, target: str, interface: str) -> Connection:
    return Connection(
        source=ConnectionEndpoint(entity=source),
        target=ConnectionEndpoint(entity=target),
        interface=InterfaceRef(name=interface),
    )


def _port(node_id: str, direction: str, name: str) -> VizPort:
    dir_tag = "req" if direction == "requires" else "prov"
    return VizPort(
        id=f"{node_id}.{dir_tag}.{name}",
        node_id=node_id,
        interface_name=name,
        interface_version=None,
        direction=direction,  # type: ignore[arg-type]
    )


def _node(node_id: str, ports: list[VizPort] | None = None) -> VizNode:
    return VizNode(
        id=node_id,
        label=node_id,
        title=None,
        kind="component",
        entity_path=node_id,
        ports=ports or [],
    )


def _edge(src_port: str, tgt_port: str) -> VizEdge:
    return VizEdge(
        id=f"edge.{src_port}--{tgt_port}",
        source_port_id=src_port,
        target_port_id=tgt_port,
        label="Iface",
        interface_name="Iface",
    )


def _simple_diagram(
    children: list[VizNode],
    peripheral_nodes: list[VizNode] | None = None,
    edges: list[VizEdge] | None = None,
) -> VizDiagram:
    """Build a minimal VizDiagram from explicit child/peripheral/edge lists."""
    root = VizBoundary(
        id="Root",
        label="Root",
        title=None,
        kind="system",
        entity_path="Root",
        children=children,
    )
    return VizDiagram(
        id="diagram.Root",
        title="Root",
        description=None,
        root=root,
        peripheral_nodes=peripheral_nodes or [],
        edges=edges or [],
    )


# ###############
# LayoutConfig
# ###############


def test_layout_config_defaults() -> None:
    """Default config has sensible non-zero values."""
    cfg = LayoutConfig()
    assert cfg.node_width > 0
    assert cfg.node_height > 0
    assert cfg.layer_gap > 0
    assert cfg.node_gap > 0
    assert cfg.peripheral_gap > 0
    assert cfg.boundary_padding > 0


def test_compute_layout_uses_custom_config() -> None:
    """A custom LayoutConfig is applied to node dimensions."""
    comp = Component(name="Sys", components=[Component(name="A")])
    diagram = build_viz_diagram(comp)
    cfg = LayoutConfig(node_width=200.0, node_height=80.0)
    plan = compute_layout(diagram, config=cfg)
    nl = next(iter(plan.nodes.values()))
    assert nl.width == 200.0
    assert nl.height == 80.0


# ###############
# Empty / minimal diagrams
# ###############


def test_empty_diagram_returns_plan() -> None:
    """A diagram with no children and no peripherals still produces a plan."""
    comp = Component(name="Empty")
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    assert isinstance(plan, LayoutPlan)
    assert plan.diagram_id == diagram.id


def test_empty_diagram_has_root_boundary() -> None:
    """Root boundary is always present in the plan."""
    comp = Component(name="Empty")
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    assert diagram.root.id in plan.boundaries


def test_empty_diagram_total_dimensions_positive() -> None:
    """Total dimensions are positive even for an empty diagram."""
    comp = Component(name="Empty")
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    assert plan.total_width > 0
    assert plan.total_height > 0


def test_single_child_node_has_layout() -> None:
    """A single child node receives a NodeLayout entry."""
    comp = Component(name="Sys", components=[Component(name="A")])
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    assert len(plan.nodes) == 1


# ###############
# Layer assignment
# ###############


def test_two_connected_nodes_in_different_layers() -> None:
    """Nodes connected by an edge are placed in different layers (different x)."""
    a_req = _port("A", "requires", "Iface")
    b_prov = _port("B", "provides", "Iface")
    a = _node("A", [a_req])
    b = _node("B", [b_prov])
    edge = _edge(a_req.id, b_prov.id)
    diagram = _simple_diagram([a, b], edges=[edge])
    plan = compute_layout(diagram)
    assert plan.nodes["A"].x != plan.nodes["B"].x


def test_source_node_left_of_sink_node() -> None:
    """The requesting node (source) is placed to the left of the provider (target)."""
    a_req = _port("A", "requires", "Iface")
    b_prov = _port("B", "provides", "Iface")
    a = _node("A", [a_req])
    b = _node("B", [b_prov])
    edge = _edge(a_req.id, b_prov.id)
    diagram = _simple_diagram([a, b], edges=[edge])
    plan = compute_layout(diagram)
    assert plan.nodes["A"].x < plan.nodes["B"].x


def test_three_node_chain_left_to_right_order() -> None:
    """A → B → C chain: A is leftmost, C is rightmost."""
    a_req = _port("A", "requires", "AB")
    b_prov_ab = _port("B", "provides", "AB")
    b_req = _port("B", "requires", "BC")
    c_prov = _port("C", "provides", "BC")
    a = _node("A", [a_req])
    b = _node("B", [b_prov_ab, b_req])
    c = _node("C", [c_prov])
    edges = [_edge(a_req.id, b_prov_ab.id), _edge(b_req.id, c_prov.id)]
    diagram = _simple_diagram([a, b, c], edges=edges)
    plan = compute_layout(diagram)
    assert plan.nodes["A"].x < plan.nodes["B"].x < plan.nodes["C"].x


def test_three_node_chain_three_distinct_x_positions() -> None:
    """Each node in a 3-layer chain occupies its own distinct x column."""
    a_req = _port("A", "requires", "AB")
    b_prov_ab = _port("B", "provides", "AB")
    b_req = _port("B", "requires", "BC")
    c_prov = _port("C", "provides", "BC")
    a = _node("A", [a_req])
    b = _node("B", [b_prov_ab, b_req])
    c = _node("C", [c_prov])
    edges = [_edge(a_req.id, b_prov_ab.id), _edge(b_req.id, c_prov.id)]
    diagram = _simple_diagram([a, b, c], edges=edges)
    plan = compute_layout(diagram)
    xs = {plan.nodes["A"].x, plan.nodes["B"].x, plan.nodes["C"].x}
    assert len(xs) == 3


def test_disconnected_nodes_assigned_layer_zero() -> None:
    """Nodes with no edges all land in the same (leftmost) column."""
    a = _node("A")
    b = _node("B")
    diagram = _simple_diagram([a, b])
    plan = compute_layout(diagram)
    assert plan.nodes["A"].x == plan.nodes["B"].x


def test_diamond_graph_max_layer_correct() -> None:
    """A → B, A → C, B → D, C → D: D must be in layer 2 (rightmost)."""
    a_req_b = _port("A", "requires", "AB")
    a_req_c = _port("A", "requires", "AC")
    b_prov = _port("B", "provides", "AB")
    b_req = _port("B", "requires", "BD")
    c_prov = _port("C", "provides", "AC")
    c_req = _port("C", "requires", "CD")
    d_prov_b = _port("D", "provides", "BD")
    d_prov_c = _port("D", "provides", "CD")
    a = _node("A", [a_req_b, a_req_c])
    b = _node("B", [b_prov, b_req])
    c = _node("C", [c_prov, c_req])
    d = _node("D", [d_prov_b, d_prov_c])
    edges = [
        _edge(a_req_b.id, b_prov.id),
        _edge(a_req_c.id, c_prov.id),
        _edge(b_req.id, d_prov_b.id),
        _edge(c_req.id, d_prov_c.id),
    ]
    diagram = _simple_diagram([a, b, c, d], edges=edges)
    plan = compute_layout(diagram)
    assert plan.nodes["A"].x < plan.nodes["B"].x
    assert plan.nodes["A"].x < plan.nodes["C"].x
    assert plan.nodes["B"].x < plan.nodes["D"].x
    assert plan.nodes["C"].x < plan.nodes["D"].x


# ###############
# Crossing minimisation
# ###############


def test_crossing_minimisation_does_not_change_layer_x() -> None:
    """Crossing minimisation only changes y-order, not x-columns."""
    a_req = _port("A", "requires", "Iface")
    b_prov = _port("B", "provides", "Iface")
    a = _node("A", [a_req])
    b = _node("B", [b_prov])
    edge = _edge(a_req.id, b_prov.id)
    diagram = _simple_diagram([a, b], edges=[edge])
    cfg = LayoutConfig()
    plan = compute_layout(diagram, config=cfg)
    # A and B must still be in different columns.
    assert plan.nodes["A"].x != plan.nodes["B"].x


def test_nodes_within_same_layer_have_different_y() -> None:
    """Two disconnected nodes in the same layer (same x) have distinct y values."""
    a = _node("A")
    b = _node("B")
    diagram = _simple_diagram([a, b])
    plan = compute_layout(diagram)
    assert plan.nodes["A"].y != plan.nodes["B"].y


# ###############
# Peripheral node classification
# ###############


def test_requires_terminal_placed_left_of_boundary() -> None:
    """A 'requires' terminal node (LEFT peripheral) is left of the root boundary."""
    comp = Component(
        name="Sys",
        requires=[_iref("InIface")],
        components=[Component(name="A")],
    )
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    boundary_x = plan.boundaries[diagram.root.id].x
    terminal = next(n for n in diagram.peripheral_nodes if n.kind == "terminal")
    assert plan.nodes[terminal.id].x < boundary_x


def test_provides_terminal_placed_right_of_boundary() -> None:
    """A 'provides' terminal node (RIGHT peripheral) is right of the root boundary."""
    comp = Component(
        name="Sys",
        provides=[_iref("OutIface")],
        components=[Component(name="A")],
    )
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    bl = plan.boundaries[diagram.root.id]
    boundary_right = bl.x + bl.width
    terminal = next(n for n in diagram.peripheral_nodes if n.kind == "terminal")
    assert plan.nodes[terminal.id].x >= boundary_right


def test_external_source_placed_left_of_boundary() -> None:
    """An external node that sources edges (has requires ports) goes LEFT."""
    ext_req = _port("Ext", "requires", "Iface")
    a_prov = _port("A", "provides", "Iface")
    ext = _node("Ext", [ext_req])
    a = _node("A", [a_prov])
    edge = _edge(ext_req.id, a_prov.id)
    diagram = _simple_diagram([a], peripheral_nodes=[ext], edges=[edge])
    plan = compute_layout(diagram)
    boundary_x = plan.boundaries["Root"].x
    assert plan.nodes["Ext"].x < boundary_x


def test_external_sink_placed_right_of_boundary() -> None:
    """An external node that targets edges (has provides ports) goes RIGHT."""
    a_req = _port("A", "requires", "Iface")
    ext_prov = _port("Ext", "provides", "Iface")
    a = _node("A", [a_req])
    ext = _node("Ext", [ext_prov])
    edge = _edge(a_req.id, ext_prov.id)
    diagram = _simple_diagram([a], peripheral_nodes=[ext], edges=[edge])
    plan = compute_layout(diagram)
    bl = plan.boundaries["Root"]
    boundary_right = bl.x + bl.width
    assert plan.nodes["Ext"].x >= boundary_right


def test_unconnected_peripheral_with_requires_port_goes_left() -> None:
    """Peripheral with only a requires port and no edges is placed LEFT."""
    req = _port("P", "requires", "X")
    p = _node("P", [req])
    a = _node("A")
    diagram = _simple_diagram([a], peripheral_nodes=[p])
    plan = compute_layout(diagram)
    boundary_x = plan.boundaries["Root"].x
    assert plan.nodes["P"].x < boundary_x


def test_unconnected_peripheral_with_provides_port_goes_right() -> None:
    """Peripheral with only a provides port and no edges is placed RIGHT."""
    prov = _port("P", "provides", "X")
    p = _node("P", [prov])
    a = _node("A")
    diagram = _simple_diagram([a], peripheral_nodes=[p])
    plan = compute_layout(diagram)
    bl = plan.boundaries["Root"]
    boundary_right = bl.x + bl.width
    assert plan.nodes["P"].x >= boundary_right


# ###############
# Port anchors
# ###############


def test_requires_port_anchored_to_left_edge() -> None:
    """A requires port anchor has x equal to the node's left edge."""
    req = _port("A", "requires", "Iface")
    a = _node("A", [req])
    diagram = _simple_diagram([a])
    plan = compute_layout(diagram)
    nl = plan.nodes["A"]
    anchor = plan.port_anchors[req.id]
    assert anchor.x == pytest.approx(nl.x)


def test_provides_port_anchored_to_right_edge() -> None:
    """A provides port anchor has x equal to the node's right edge."""
    prov = _port("A", "provides", "Iface")
    a = _node("A", [prov])
    diagram = _simple_diagram([a])
    plan = compute_layout(diagram)
    nl = plan.nodes["A"]
    anchor = plan.port_anchors[prov.id]
    assert anchor.x == pytest.approx(nl.x + nl.width)


def test_single_port_vertically_centred_on_node() -> None:
    """A single port on a side is anchored at y = node.y + height/2."""
    req = _port("A", "requires", "Iface")
    a = _node("A", [req])
    diagram = _simple_diagram([a])
    plan = compute_layout(diagram)
    nl = plan.nodes["A"]
    anchor = plan.port_anchors[req.id]
    assert anchor.y == pytest.approx(nl.y + nl.height / 2)


def test_two_requires_ports_have_different_y() -> None:
    """Two requires ports on the same node have distinct y anchors."""
    p1 = _port("A", "requires", "Iface1")
    p2 = _port("A", "requires", "Iface2")
    a = _node("A", [p1, p2])
    diagram = _simple_diagram([a])
    plan = compute_layout(diagram)
    assert plan.port_anchors[p1.id].y != plan.port_anchors[p2.id].y


def test_multiple_ports_evenly_spaced_within_node_height() -> None:
    """Three requires ports are anchored within the node's vertical extent."""
    ports = [_port("A", "requires", f"I{i}") for i in range(3)]
    a = _node("A", ports)
    diagram = _simple_diagram([a])
    plan = compute_layout(diagram)
    nl = plan.nodes["A"]
    for p in ports:
        anc = plan.port_anchors[p.id]
        assert nl.y < anc.y < nl.y + nl.height


def test_provides_and_requires_ports_on_opposite_sides() -> None:
    """Requires and provides ports on the same node are anchored to opposite x edges."""
    req = _port("A", "requires", "In")
    prov = _port("A", "provides", "Out")
    a = _node("A", [req, prov])
    diagram = _simple_diagram([a])
    plan = compute_layout(diagram)
    nl = plan.nodes["A"]
    assert plan.port_anchors[req.id].x == pytest.approx(nl.x)
    assert plan.port_anchors[prov.id].x == pytest.approx(nl.x + nl.width)


def test_root_boundary_requires_port_on_left_edge() -> None:
    """Root boundary requires port is anchored to the left edge of the boundary."""
    comp = Component(name="Sys", requires=[_iref("InIface")])
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    bl = plan.boundaries[diagram.root.id]
    req_port = next(p for p in diagram.root.ports if p.direction == "requires")
    anchor = plan.port_anchors[req_port.id]
    assert anchor.x == pytest.approx(bl.x)


def test_root_boundary_provides_port_on_right_edge() -> None:
    """Root boundary provides port is anchored to the right edge of the boundary."""
    comp = Component(name="Sys", provides=[_iref("OutIface")])
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    bl = plan.boundaries[diagram.root.id]
    prov_port = next(p for p in diagram.root.ports if p.direction == "provides")
    anchor = plan.port_anchors[prov_port.id]
    assert anchor.x == pytest.approx(bl.x + bl.width)


# ###############
# Edge routes
# ###############


def test_edge_route_has_two_waypoints() -> None:
    """A straight-line edge route has exactly two waypoints."""
    a_req = _port("A", "requires", "Iface")
    b_prov = _port("B", "provides", "Iface")
    a = _node("A", [a_req])
    b = _node("B", [b_prov])
    edge = _edge(a_req.id, b_prov.id)
    diagram = _simple_diagram([a, b], edges=[edge])
    plan = compute_layout(diagram)
    assert edge.id in plan.edge_routes
    assert len(plan.edge_routes[edge.id].waypoints) == 2


def test_edge_route_starts_at_source_port_anchor() -> None:
    """First waypoint of an edge route matches the source port anchor."""
    a_req = _port("A", "requires", "Iface")
    b_prov = _port("B", "provides", "Iface")
    a = _node("A", [a_req])
    b = _node("B", [b_prov])
    edge = _edge(a_req.id, b_prov.id)
    diagram = _simple_diagram([a, b], edges=[edge])
    plan = compute_layout(diagram)
    src_anc = plan.port_anchors[a_req.id]
    first_wp = plan.edge_routes[edge.id].waypoints[0]
    assert first_wp == pytest.approx((src_anc.x, src_anc.y))


def test_edge_route_ends_at_target_port_anchor() -> None:
    """Last waypoint of an edge route matches the target port anchor."""
    a_req = _port("A", "requires", "Iface")
    b_prov = _port("B", "provides", "Iface")
    a = _node("A", [a_req])
    b = _node("B", [b_prov])
    edge = _edge(a_req.id, b_prov.id)
    diagram = _simple_diagram([a, b], edges=[edge])
    plan = compute_layout(diagram)
    tgt_anc = plan.port_anchors[b_prov.id]
    last_wp = plan.edge_routes[edge.id].waypoints[-1]
    assert last_wp == pytest.approx((tgt_anc.x, tgt_anc.y))


def test_edge_with_unresolvable_port_not_in_routes() -> None:
    """Edges whose port anchors cannot be resolved are omitted from edge_routes."""
    # Build a diagram then inject a fake edge with unknown port IDs.
    comp = Component(name="Sys")
    diagram = build_viz_diagram(comp)
    # Manually inject an unresolvable edge.
    fake_edge = VizEdge(
        id="edge.ghost.req--ghost.prov",
        source_port_id="ghost.req.Unknown",
        target_port_id="ghost.prov.Unknown",
        label="Unknown",
        interface_name="Unknown",
    )
    diagram.edges.append(fake_edge)
    plan = compute_layout(diagram)
    assert fake_edge.id not in plan.edge_routes


# ###############
# Boundary sizing
# ###############


def test_boundary_contains_all_child_nodes() -> None:
    """Every child node lies within the root boundary rectangle."""
    comp = Component(
        name="Sys",
        components=[Component(name="A"), Component(name="B"), Component(name="C")],
    )
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    bl = plan.boundaries[diagram.root.id]
    for nl in plan.nodes.values():
        if nl.node_id in {c.id for c in diagram.root.children}:
            assert nl.x >= bl.x
            assert nl.y >= bl.y
            assert nl.x + nl.width <= bl.x + bl.width
            assert nl.y + nl.height <= bl.y + bl.height


def test_boundary_padding_applied() -> None:
    """The boundary is wider than its single child by at least 2× boundary_padding."""
    comp = Component(name="Sys", components=[Component(name="A")])
    diagram = build_viz_diagram(comp)
    cfg = LayoutConfig(boundary_padding=50.0)
    plan = compute_layout(diagram, config=cfg)
    bl = plan.boundaries[diagram.root.id]
    assert bl.width >= cfg.node_width + 2 * cfg.boundary_padding
    assert bl.height >= cfg.node_height + 2 * cfg.boundary_padding


def test_layer_gap_increases_boundary_width() -> None:
    """A larger layer_gap produces a wider root boundary for multi-layer diagrams."""
    a_req = _port("A", "requires", "Iface")
    b_prov = _port("B", "provides", "Iface")
    a = _node("A", [a_req])
    b = _node("B", [b_prov])
    edge = _edge(a_req.id, b_prov.id)
    diagram = _simple_diagram([a, b], edges=[edge])

    plan_small = compute_layout(diagram, config=LayoutConfig(layer_gap=20.0))
    plan_large = compute_layout(diagram, config=LayoutConfig(layer_gap=200.0))
    assert plan_large.boundaries["Root"].width > plan_small.boundaries["Root"].width


# ###############
# Total diagram dimensions
# ###############


def test_total_width_includes_left_peripheral_zone() -> None:
    """Adding a left peripheral increases total_width."""
    a = _node("A")
    diagram_no_peri = _simple_diagram([a])
    plan_no = compute_layout(diagram_no_peri)

    req = _port("P", "requires", "X")
    p = _node("P", [req])
    diagram_with = _simple_diagram([a], peripheral_nodes=[p])
    plan_with = compute_layout(diagram_with)
    assert plan_with.total_width > plan_no.total_width


def test_total_width_includes_right_peripheral_zone() -> None:
    """Adding a right peripheral increases total_width."""
    a = _node("A")
    diagram_no_peri = _simple_diagram([a])
    plan_no = compute_layout(diagram_no_peri)

    prov = _port("P", "provides", "X")
    p = _node("P", [prov])
    diagram_with = _simple_diagram([a], peripheral_nodes=[p])
    plan_with = compute_layout(diagram_with)
    assert plan_with.total_width > plan_no.total_width


def test_peripheral_nodes_outside_boundary_in_total_width() -> None:
    """The total width is at least as wide as boundary + both peripheral zones."""
    comp = Component(
        name="Sys",
        requires=[_iref("In")],
        provides=[_iref("Out")],
        components=[Component(name="A")],
    )
    diagram = build_viz_diagram(comp)
    cfg = LayoutConfig()
    plan = compute_layout(diagram, config=cfg)
    bl = plan.boundaries[diagram.root.id]
    # Both terminal zones must be accounted for.
    assert plan.total_width >= bl.x + bl.width + cfg.peripheral_gap + cfg.peripheral_node_width


# ###############
# Integration: build_viz_diagram → compute_layout
# ###############


def test_ecommerce_system_produces_complete_plan() -> None:
    """Full integration: ecommerce system with multiple components and connections."""
    sys = System(
        name="ECommerce",
        components=[
            Component(
                name="OrderService",
                requires=[_iref("PaymentRequest")],
                provides=[_iref("OrderRequest")],
            ),
            Component(
                name="PaymentService",
                provides=[_iref("PaymentRequest")],
            ),
            Component(
                name="NotificationService",
                requires=[_iref("OrderRequest")],
            ),
        ],
        connections=[
            _conn("OrderService", "PaymentService", "PaymentRequest"),
            _conn("NotificationService", "OrderService", "OrderRequest"),
        ],
    )
    diagram = build_viz_diagram(sys)
    plan = compute_layout(diagram)

    # All three children have layouts.
    child_ids = {c.id for c in diagram.root.children}
    assert child_ids <= plan.nodes.keys()

    # Root boundary is present.
    assert diagram.root.id in plan.boundaries

    # All edges are routed.
    assert len(plan.edge_routes) == len(diagram.edges)


def test_ecommerce_order_service_left_of_payment_service() -> None:
    """OrderService (requirer) is to the left of PaymentService (provider)."""
    sys = System(
        name="ECommerce",
        components=[
            Component(
                name="OrderService",
                requires=[_iref("PaymentRequest")],
            ),
            Component(
                name="PaymentService",
                provides=[_iref("PaymentRequest")],
            ),
        ],
        connections=[_conn("OrderService", "PaymentService", "PaymentRequest")],
    )
    diagram = build_viz_diagram(sys)
    plan = compute_layout(diagram)
    order_id = next(c.id for c in diagram.root.children if c.label == "OrderService")
    payment_id = next(c.id for c in diagram.root.children if c.label == "PaymentService")
    assert plan.nodes[order_id].x < plan.nodes[payment_id].x


def test_external_actor_resolved_and_positioned() -> None:
    """An external actor resolved via external_entities receives a layout entry."""
    stripe = Component(name="Stripe", is_external=True, provides=[_iref("PaymentGateway")])
    sys = System(
        name="ECommerce",
        components=[
            Component(name="OrderService", requires=[_iref("PaymentGateway")]),
        ],
        connections=[_conn("OrderService", "Stripe", "PaymentGateway")],
    )
    diagram = build_viz_diagram(sys, external_entities={"Stripe": stripe})
    plan = compute_layout(diagram)
    stripe_node = next(n for n in diagram.peripheral_nodes if n.label == "Stripe")
    assert stripe_node.id in plan.nodes


def test_external_actor_right_of_boundary_when_it_provides() -> None:
    """An external provider (target of edges) is placed right of the boundary."""
    stripe = Component(name="Stripe", is_external=True, provides=[_iref("PaymentGateway")])
    sys = System(
        name="ECommerce",
        components=[
            Component(name="OrderService", requires=[_iref("PaymentGateway")]),
        ],
        connections=[_conn("OrderService", "Stripe", "PaymentGateway")],
    )
    diagram = build_viz_diagram(sys, external_entities={"Stripe": stripe})
    plan = compute_layout(diagram)
    bl = plan.boundaries[diagram.root.id]
    stripe_node = next(n for n in diagram.peripheral_nodes if n.label == "Stripe")
    assert plan.nodes[stripe_node.id].x >= bl.x + bl.width


def test_all_ports_in_diagram_have_anchors() -> None:
    """Every port in a topology diagram has a corresponding PortAnchor."""
    sys = System(
        name="ECommerce",
        requires=[_iref("ClientRequest")],
        provides=[_iref("ClientResponse")],
        components=[
            Component(name="A", requires=[_iref("BService")]),
            Component(name="B", provides=[_iref("BService")]),
        ],
        connections=[_conn("A", "B", "BService")],
    )
    diagram = build_viz_diagram(sys)
    plan = compute_layout(diagram)
    from archml.views.topology import collect_all_ports

    all_ports = collect_all_ports(diagram)
    for port_id in all_ports:
        assert port_id in plan.port_anchors, f"Missing anchor for port {port_id}"


def test_plan_diagram_id_matches_viz_diagram_id() -> None:
    """plan.diagram_id matches the VizDiagram's id."""
    comp = Component(name="Sys")
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    assert plan.diagram_id == diagram.id
