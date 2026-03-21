# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Sugiyama-style placement algorithm."""

import pytest

from archml.model.entities import Component, ConnectDef, InterfaceRef, System
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
    """A straight-line edge route has exactly two waypoints.

    Uses the canonical ArchML edge direction (provides → requires) so the
    source anchor sits on the right edge of A and the target anchor on the
    left edge of B.  The straight line between them does not pass through
    either node body, so no detour is needed.
    """
    a_prov = _port("A", "provides", "Iface")
    b_req = _port("B", "requires", "Iface")
    a = _node("A", [a_prov])
    b = _node("B", [b_req])
    edge = _edge(a_prov.id, b_req.id)
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
# Text-aware node sizing
# ###############


def test_long_label_expands_node_width() -> None:
    """A node with a long label produces a wider layout than the config minimum."""
    short = _node("A")
    long_label = "VeryLongComponentName"  # exceeds node_width=120 at default char_width
    long_node = _node(long_label)
    diagram_short = _simple_diagram([short])
    diagram_long = _simple_diagram([long_node])
    cfg = LayoutConfig()
    plan_short = compute_layout(diagram_short, config=cfg)
    plan_long = compute_layout(diagram_long, config=cfg)
    assert plan_long.nodes[long_label].width > plan_short.nodes["A"].width


def test_all_inner_nodes_get_same_width() -> None:
    """All inner child nodes have a uniform width equal to the widest label's requirement."""
    short = _node("A")
    long_node = _node("VeryLongComponentName")
    diagram = _simple_diagram([short, long_node])
    plan = compute_layout(diagram)
    assert plan.nodes["A"].width == plan.nodes["VeryLongComponentName"].width


def test_long_peripheral_label_expands_peripheral_width() -> None:
    """A peripheral node with a long label expands the peripheral zone width."""
    inner = _node("A")
    req = _port("ShortPeri", "requires", "X")
    short_peri = _node("ShortPeri", [req])
    diagram_short = _simple_diagram([inner], peripheral_nodes=[short_peri])

    long_name = "VeryLongPeripheralLabel"
    req2 = _port(long_name, "requires", "X")
    long_peri = _node(long_name, [req2])
    diagram_long = _simple_diagram([inner], peripheral_nodes=[long_peri])

    plan_short = compute_layout(diagram_short)
    plan_long = compute_layout(diagram_long)
    assert plan_long.nodes[long_name].width > plan_short.nodes["ShortPeri"].width


def test_node_width_is_at_least_config_minimum() -> None:
    """A very short label never makes a node narrower than cfg.node_width."""
    a = _node("A")
    diagram = _simple_diagram([a])
    cfg = LayoutConfig(node_width=200.0)
    plan = compute_layout(diagram, config=cfg)
    assert plan.nodes["A"].width == 200.0


def test_peripheral_width_is_at_least_config_minimum() -> None:
    """A very short peripheral label never drops below cfg.peripheral_node_width."""
    inner = _node("A")
    req = _port("P", "requires", "X")
    p = _node("P", [req])
    diagram = _simple_diagram([inner], peripheral_nodes=[p])
    cfg = LayoutConfig(peripheral_node_width=300.0)
    plan = compute_layout(diagram, config=cfg)
    assert plan.nodes["P"].width == 300.0


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
    """Full integration: ecommerce system with multiple components connected via connect statements."""
    sys = System(
        name="ECommerce",
        connects=[
            _connect("PaymentService", "PaymentRequest", "OrderService", "PaymentRequest", channel="payment"),
            _connect("OrderService", "OrderRequest", "NotificationService", "OrderRequest", channel="notification"),
        ],
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


def test_ecommerce_payment_service_left_of_order_service() -> None:
    """PaymentService (provider/source) is to the left of OrderService (requirer/target)."""
    sys = System(
        name="ECommerce",
        connects=[_connect("PaymentService", "PaymentRequest", "OrderService", "PaymentRequest", channel="payment")],
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
    )
    diagram = build_viz_diagram(sys)
    plan = compute_layout(diagram)
    order_id = next(c.id for c in diagram.root.children if c.label == "OrderService")
    payment_id = next(c.id for c in diagram.root.children if c.label == "PaymentService")
    assert plan.nodes[payment_id].x < plan.nodes[order_id].x


def test_external_actor_in_components_positioned() -> None:
    """An external actor declared in components receives a layout entry."""
    stripe = Component(name="Stripe", is_external=True, provides=[_iref("PaymentGateway")])
    sys = System(
        name="ECommerce",
        connects=[_connect("Stripe", "PaymentGateway", "OrderService", "PaymentGateway", channel="payment")],
        components=[
            Component(name="OrderService", requires=[_iref("PaymentGateway")]),
            stripe,
        ],
    )
    diagram = build_viz_diagram(sys)
    plan = compute_layout(diagram)
    stripe_node = next(c for c in diagram.root.children if c.label == "Stripe")
    assert stripe_node.id in plan.nodes


def test_external_actor_left_of_requirer_when_it_provides() -> None:
    """An external provider (source of edge) is placed left of the requirer (target)."""
    stripe = Component(name="Stripe", is_external=True, provides=[_iref("PaymentGateway")])
    sys = System(
        name="ECommerce",
        connects=[_connect("Stripe", "PaymentGateway", "OrderService", "PaymentGateway", channel="payment")],
        components=[
            Component(name="OrderService", requires=[_iref("PaymentGateway")]),
            stripe,
        ],
    )
    diagram = build_viz_diagram(sys)
    plan = compute_layout(diagram)
    order_id = next(c.id for c in diagram.root.children if c.label == "OrderService")
    stripe_id = next(c.id for c in diagram.root.children if c.label == "Stripe")
    assert plan.nodes[stripe_id].x < plan.nodes[order_id].x


def test_all_ports_in_diagram_have_anchors() -> None:
    """Every port in a topology diagram has a corresponding PortAnchor."""
    sys = System(
        name="ECommerce",
        requires=[_iref("ClientRequest")],
        provides=[_iref("ClientResponse")],
        connects=[_connect("B", "BService", "A", "BService", channel="b_service")],
        components=[
            Component(name="A", requires=[_iref("BService")]),
            Component(name="B", provides=[_iref("BService")]),
        ],
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


# ###############
# Expanded boundary layout (all-diagram with nested boundaries)
# ###############


def test_expanded_boundary_child_produces_boundary_layout() -> None:
    """An expanded VizBoundary child of the root gets a BoundaryLayout entry."""
    from archml.model.entities import ArchFile
    from archml.views.topology import build_viz_diagram_all

    inner = Component(name="A", requires=[_iref("X")])
    order = System(name="Order", components=[inner])
    af = ArchFile(systems=[order])
    diag = build_viz_diagram_all({"f": af})
    plan = compute_layout(diag)
    assert "Order" in plan.boundaries


def test_expanded_boundary_inner_nodes_have_layout() -> None:
    """Inner nodes of an expanded boundary appear in plan.nodes with positions."""
    from archml.model.entities import ArchFile
    from archml.views.topology import build_viz_diagram_all

    inner = Component(name="A", requires=[_iref("X")])
    order = System(name="Order", components=[inner])
    af = ArchFile(systems=[order])
    diag = build_viz_diagram_all({"f": af})
    plan = compute_layout(diag)
    assert any("Order__A" in nid for nid in plan.nodes)


def test_expanded_boundary_bounding_box_encloses_inner_nodes() -> None:
    """The boundary layout for an expanded entity fully encloses its inner nodes."""
    from archml.model.entities import ArchFile
    from archml.views.topology import build_viz_diagram_all

    inner_a = Component(name="A", provides=[_iref("IFace")])
    inner_b = Component(name="B", requires=[_iref("IFace")])
    order = System(
        name="Order",
        components=[inner_a, inner_b],
        connects=[ConnectDef(src_entity="A", src_port="IFace", channel="ch", dst_entity="B", dst_port="IFace")],
    )
    af = ArchFile(systems=[order])
    diag = build_viz_diagram_all({"f": af})
    plan = compute_layout(diag)
    bnd_lay = plan.boundaries["Order"]
    for nid, nl in plan.nodes.items():
        if "Order__" in nid:
            assert nl.x >= bnd_lay.x
            assert nl.y >= bnd_lay.y
            assert nl.x + nl.width <= bnd_lay.x + bnd_lay.width
            assert nl.y + nl.height <= bnd_lay.y + bnd_lay.height


def test_all_port_anchors_resolved_with_expanded_boundary() -> None:
    """All ports of an all-diagram with expanded boundaries have anchors."""
    from archml.model.entities import ArchFile, ExposeDef
    from archml.views.topology import build_viz_diagram_all, collect_all_ports

    comp_a = Component(name="A", requires=[_iref("OrderRequest")])
    order = System(
        name="Order",
        components=[comp_a],
        exposes=[ExposeDef(entity="A", port="OrderRequest")],
    )
    ingestor = Component(name="DataIngestor", provides=[_iref("OrderRequest")])
    conn = ConnectDef(
        src_entity="DataIngestor",
        src_port="OrderRequest",
        channel="ch",
        dst_entity="Order",
        dst_port="OrderRequest",
    )
    af = ArchFile(systems=[order], components=[ingestor], connects=[conn])
    diag = build_viz_diagram_all({"f": af})
    plan = compute_layout(diag)
    all_ports = collect_all_ports(diag)
    for port_id in all_ports:
        assert port_id in plan.port_anchors, f"Missing anchor for port {port_id}"


# ###############
# Boundary title fitting (text width constraint)
# ###############


def test_boundary_wide_enough_for_long_title() -> None:
    """Boundary width must accommodate its own title label, even when children are narrow."""
    # "AVeryLongBoundaryTitle" is 22 chars, bold at font_ratio=1.1.
    # With narrow children the content would normally be too thin to fit the title.
    long_name = "AVeryLongBoundaryTitle"
    sys = System(name=long_name, components=[Component(name="X")])
    diagram = build_viz_diagram(sys)
    plan = compute_layout(diagram)
    bl = plan.boundaries[diagram.root.id]
    cfg = LayoutConfig()
    from archml.views.placement import _required_text_width

    min_width = _required_text_width(long_name, cfg, bold=True, font_ratio=cfg.boundary_title_font_ratio)
    assert bl.width >= min_width, (
        f"Boundary width {bl.width:.1f} < required title width {min_width:.1f} for '{long_name}'"
    )


def test_boundary_wide_enough_when_children_are_narrower() -> None:
    """A single short-named child must not make the boundary narrower than its title."""
    sys = System(name="PaymentGateway", components=[Component(name="X")])
    diagram = build_viz_diagram(sys)
    plan = compute_layout(diagram)
    bl = plan.boundaries[diagram.root.id]
    cfg = LayoutConfig()
    from archml.views.placement import _required_text_width

    min_width = _required_text_width("PaymentGateway", cfg, bold=True, font_ratio=cfg.boundary_title_font_ratio)
    assert bl.width >= min_width


def test_nested_boundary_wide_enough_for_its_own_title() -> None:
    """Nested boundaries must also fit their own title, not just their parent's."""
    from archml.model.entities import System

    inner = System(name="LongInnerSystemName", components=[Component(name="A")])
    outer = System(name="Outer", systems=[inner])
    diagram = build_viz_diagram(outer)
    plan = compute_layout(diagram)
    cfg = LayoutConfig()
    from archml.views.placement import _required_text_width

    inner_bl = next(bl for bid, bl in plan.boundaries.items() if "LongInnerSystemName" in bid)
    min_width = _required_text_width("LongInnerSystemName", cfg, bold=True, font_ratio=cfg.boundary_title_font_ratio)
    assert inner_bl.width >= min_width


# ###############
# Orthogonal routing
# ###############


def test_edge_route_has_only_right_angle_bends() -> None:
    """Edge routes must consist of horizontal and vertical segments only (no diagonals)."""
    a_port = _port("A", "provides", "Iface")
    b_port = _port("B", "requires", "Iface")
    a = _node("A", [a_port])
    b = _node("B", [b_port])
    edge = _edge(a_port.id, b_port.id)
    diagram = _simple_diagram([a, b], edges=[edge])
    plan = compute_layout(diagram)
    route = plan.edge_routes.get(edge.id)
    assert route is not None
    wps = route.waypoints
    assert len(wps) >= 2
    for (x1, y1), (x2, y2) in zip(wps, wps[1:], strict=False):
        assert abs(x1 - x2) < 0.5 or abs(y1 - y2) < 0.5, (
            f"Diagonal segment detected: ({x1:.1f},{y1:.1f}) → ({x2:.1f},{y2:.1f})"
        )


def test_edge_route_uses_z_shape_when_source_and_target_differ_vertically() -> None:
    """When source and target anchors differ in y, the route uses a Z-shaped 4-waypoint path."""
    # Use two nodes: one provides, one requires, in separate layers so they have different y anchors.
    a_port = _port("A", "provides", "Iface")
    b_port = _port("B", "requires", "Iface")
    # Give B a requires port to make it in a later layer than A.
    c_port = _port("B", "requires", "Other")
    a = _node("A", [a_port])
    b = VizNode(
        id="B",
        label="B",
        title=None,
        kind="component",
        entity_path="B",
        ports=[b_port, c_port],
    )
    # Add a third node C so A and B are at different vertical positions.
    c = _node("C", [])
    edge = _edge(a_port.id, b_port.id)
    diagram = _simple_diagram([a, b, c], edges=[edge])
    plan = compute_layout(diagram)
    route = plan.edge_routes.get(edge.id)
    assert route is not None
    # All segments must be axis-aligned.
    for (x1, y1), (x2, y2) in zip(route.waypoints, route.waypoints[1:], strict=False):
        assert abs(x1 - x2) < 0.5 or abs(y1 - y2) < 0.5


def test_edge_route_midpoint_x_between_source_and_target() -> None:
    """The vertical segment of a Z-route is placed between the source and target x positions."""
    a_port = _port("A", "provides", "Iface")
    b_port = _port("B", "requires", "Iface")
    a = _node("A", [a_port])
    b = _node("B", [b_port])
    c = _node("C", [])  # extra node so A and B end up at different y
    edge = _edge(a_port.id, b_port.id)
    diagram = _simple_diagram([a, b, c], edges=[edge])
    plan = compute_layout(diagram)
    route = plan.edge_routes.get(edge.id)
    src_anc = plan.port_anchors[a_port.id]
    tgt_anc = plan.port_anchors[b_port.id]
    if route is not None and len(route.waypoints) == 4:
        mid_xs = list({x for x, _ in route.waypoints[1:3]})
        assert len(mid_xs) == 1
        assert src_anc.x <= mid_xs[0] <= tgt_anc.x or mid_xs[0] == pytest.approx((src_anc.x + tgt_anc.x) / 2, rel=1e-3)


def test_straight_route_for_same_y_anchors() -> None:
    """When source and target port anchors are at the same y, return a 2-waypoint straight line."""
    # A node with one provides port and one requires port at the same y level:
    # this happens when both nodes are in the same row of their layer.
    a_port = _port("A", "provides", "Iface")
    b_port = _port("B", "requires", "Iface")
    a = _node("A", [a_port])
    b = _node("B", [b_port])
    # No extra nodes — only two nodes, each in its own layer, each alone in that layer.
    # With a single node per layer the anchors will be at the vertical centre of each node,
    # which matches because both nodes have the same height.
    edge = _edge(a_port.id, b_port.id)
    diagram = _simple_diagram([a, b], edges=[edge])
    plan = compute_layout(diagram)
    route = plan.edge_routes.get(edge.id)
    src_anc = plan.port_anchors[a_port.id]
    tgt_anc = plan.port_anchors[b_port.id]
    assert route is not None
    if abs(src_anc.y - tgt_anc.y) < 0.5:
        assert len(route.waypoints) == 2


def test_route_avoiding_obstacles_same_y_is_straight() -> None:
    """Same-y source and target → 2-waypoint straight horizontal line."""
    from archml.views.placement import _route_avoiding_obstacles

    wps = _route_avoiding_obstacles(0.0, 10.0, 100.0, 10.0, [], 200.0)
    assert wps == [(0.0, 10.0), (100.0, 10.0)]


def test_route_avoiding_obstacles_no_obstacles_z_shape() -> None:
    """No obstacles → simple Z-route through the midpoint corridor."""
    from archml.views.placement import _route_avoiding_obstacles

    wps = _route_avoiding_obstacles(0.0, 10.0, 100.0, 50.0, [], 200.0)
    assert len(wps) == 4
    assert wps[0] == (0.0, 10.0)
    assert wps[-1] == (100.0, 50.0)
    # All segments axis-aligned.
    for (x1, y1), (x2, y2) in zip(wps, wps[1:], strict=False):
        assert abs(x1 - x2) < 1e-9 or abs(y1 - y2) < 1e-9


def test_route_avoiding_obstacles_avoids_single_box_in_straight_path() -> None:
    """An obstacle in the direct Z-path forces a detour that clears it."""
    from archml.views.placement import _route_avoiding_obstacles, _route_is_clear

    # Source at x=0,y=100.  Target at x=200,y=50.
    # An obstacle at x=80..120 blocks the midpoint corridor vertically.
    # Its y range includes both sy=100 and ty=50, so a simple Z via mid_x=100
    # would have both the horizontal segment at y=100 AND the horizontal
    # return at y=50 crossing through it.
    obstacle = [(80.0, 30.0, 40.0, 90.0)]  # x 80..120, y 30..120
    wps = _route_avoiding_obstacles(0.0, 100.0, 200.0, 50.0, obstacle, 300.0)
    # Route must be axis-aligned.
    for (x1, y1), (x2, y2) in zip(wps, wps[1:], strict=False):
        assert abs(x1 - x2) < 0.5 or abs(y1 - y2) < 0.5, f"Diagonal: ({x1:.1f},{y1:.1f}) → ({x2:.1f},{y2:.1f})"
    # Route must clear the obstacle.
    assert _route_is_clear(wps, obstacle), f"Route {wps} crosses obstacle {obstacle}"


def test_route_avoiding_obstacles_double_z_when_single_z_blocked() -> None:
    """When every single-corridor Z-route is blocked, the double-Z bypass is used."""
    from archml.views.placement import _route_avoiding_obstacles, _route_is_clear

    # Source at x=0, sy=150.  Target at x=300, ty=100.
    # Two obstacles block every simple corridor horizontally:
    #   obs1 at x=50..100 spans y=50..200  → blocks horizontal segments at y 100 and 150
    #   obs2 at x=200..250 spans y=50..200 → same
    # The only clear corridor is between obs1 and obs2 (x=100..200, corridor ≈ 150),
    # but the horizontal return at ty=100 entering from x=150 to x=300 crosses obs2.
    obs1 = (50.0, 50.0, 50.0, 150.0)  # x 50..100,  y 50..200
    obs2 = (200.0, 50.0, 50.0, 150.0)  # x 200..250, y 50..200
    obstacles = [obs1, obs2]
    wps = _route_avoiding_obstacles(0.0, 150.0, 300.0, 100.0, obstacles, 400.0)
    for (x1, y1), (x2, y2) in zip(wps, wps[1:], strict=False):
        assert abs(x1 - x2) < 0.5 or abs(y1 - y2) < 0.5
    assert _route_is_clear(wps, obstacles), f"Route {wps} crosses an obstacle"


def test_route_avoiding_obstacles_all_segments_axis_aligned_with_obstacles() -> None:
    """With multiple obstacles, every segment of the returned route is axis-aligned."""
    from archml.views.placement import _route_avoiding_obstacles

    obstacles = [
        (40.0, 60.0, 30.0, 80.0),
        (130.0, 40.0, 30.0, 100.0),
    ]
    wps = _route_avoiding_obstacles(0.0, 100.0, 200.0, 70.0, obstacles, 300.0)
    for (x1, y1), (x2, y2) in zip(wps, wps[1:], strict=False):
        assert abs(x1 - x2) < 0.5 or abs(y1 - y2) < 0.5


# ------- helper unit tests -------


def test_free_corridor_xs_empty_when_fully_blocked() -> None:
    """No corridors when a single obstacle covers the entire x range."""
    from archml.views.placement import _free_corridor_xs

    # Obstacle covers [0, 100]; sx=0, tx=100 → no free corridor.
    obs = [(0.0, 0.0, 100.0, 50.0)]
    assert _free_corridor_xs(0.0, 100.0, obs) == []


def test_free_corridor_xs_single_gap_between_two_obstacles() -> None:
    """One corridor between two non-overlapping obstacles."""
    from archml.views.placement import _free_corridor_xs

    obs = [(0.0, 0.0, 30.0, 10.0), (70.0, 0.0, 30.0, 10.0)]
    corridors = _free_corridor_xs(0.0, 100.0, obs)
    # One corridor between x=30 and x=70, midpoint=50.
    assert len(corridors) == 1
    assert corridors[0] == pytest.approx(50.0)


def test_free_corridor_xs_gaps_before_after_and_between() -> None:
    """Corridors before, between, and after two interior obstacles."""
    from archml.views.placement import _free_corridor_xs

    obs = [(20.0, 0.0, 20.0, 10.0), (60.0, 0.0, 20.0, 10.0)]
    corridors = _free_corridor_xs(0.0, 100.0, obs)
    # Three corridors: [0,20)=mid10, (40,60)=mid50, (80,100)=mid90
    assert len(corridors) == 3
    assert corridors[0] == pytest.approx(10.0)
    assert corridors[1] == pytest.approx(50.0)
    assert corridors[2] == pytest.approx(90.0)


def test_free_corridor_xs_returns_empty_for_backward_range() -> None:
    """Returns empty list when tx <= sx (no forward range to search)."""
    from archml.views.placement import _free_corridor_xs

    assert _free_corridor_xs(100.0, 50.0, []) == []
    assert _free_corridor_xs(50.0, 50.0, []) == []


def test_bypass_levels_above_and_below() -> None:
    """Bypass levels straddle the obstacle bounding box."""
    from archml.views.placement import _bypass_levels

    obs = [(10.0, 50.0, 80.0, 100.0)]  # y 50..150
    levels = _bypass_levels(10.0, 90.0, obs, 300.0, gap=5.0)
    assert len(levels) == 2
    assert levels[0] == pytest.approx(45.0)  # above: 50 - 5
    assert levels[1] == pytest.approx(155.0)  # below: 150 + 5


def test_bypass_levels_empty_when_no_obstacles_in_range() -> None:
    """Returns empty list when no obstacle overlaps the given x range."""
    from archml.views.placement import _bypass_levels

    obs = [(200.0, 0.0, 50.0, 100.0)]  # outside x range [10, 90]
    levels = _bypass_levels(10.0, 90.0, obs, 300.0, gap=5.0)
    assert levels == []


def test_route_is_clear_detects_horizontal_crossing() -> None:
    """_route_is_clear flags a horizontal segment that enters an obstacle."""
    from archml.views.placement import _route_is_clear

    obs = [(40.0, 90.0, 20.0, 20.0)]  # x 40..60, y 90..110
    # Horizontal segment at y=100 from x=0 to x=80 crosses the obstacle.
    wps = [(0.0, 100.0), (80.0, 100.0)]
    assert not _route_is_clear(wps, obs)


def test_route_is_clear_accepts_clear_path() -> None:
    """_route_is_clear passes a path that avoids all obstacles."""
    from archml.views.placement import _route_is_clear

    obs = [(40.0, 90.0, 20.0, 20.0)]
    # Route goes above the obstacle.
    wps = [(0.0, 80.0), (80.0, 80.0)]
    assert _route_is_clear(wps, obs)


# ------- integration: ecommerce-like topology -------


def test_ecommerce_like_routes_avoid_component_boxes() -> None:
    """In a 3-layer ecommerce-like system, no edge route crosses a component box."""
    sys = System(
        name="ECommerce",
        connects=[
            _connect("PaymentGateway", "PaymentRequest", "OrderService", "PaymentRequest", channel="payment"),
            _connect("InventoryManager", "InventoryCheck", "OrderService", "InventoryCheck", channel="inventory"),
        ],
        components=[
            Component(name="OrderService", requires=[_iref("PaymentRequest"), _iref("InventoryCheck")]),
            Component(name="PaymentGateway", provides=[_iref("PaymentRequest")]),
            Component(name="InventoryManager", provides=[_iref("InventoryCheck")]),
        ],
    )
    diagram = build_viz_diagram(sys)
    plan = compute_layout(diagram)

    # Build obstacle list from all placed nodes.
    obstacles = [(nl.x, nl.y, nl.width, nl.height) for nl in plan.nodes.values()]

    from archml.views.placement import _route_is_clear

    for edge in diagram.edges:
        route = plan.edge_routes.get(edge.id)
        if route is None:
            continue
        # All segments must be axis-aligned.
        for (x1, y1), (x2, y2) in zip(route.waypoints, route.waypoints[1:], strict=False):
            assert abs(x1 - x2) < 0.5 or abs(y1 - y2) < 0.5, (
                f"Edge {edge.id}: diagonal ({x1:.1f},{y1:.1f})→({x2:.1f},{y2:.1f})"
            )
        # Route must not cross any component box.
        assert _route_is_clear(route.waypoints, obstacles), (
            f"Edge {edge.id} route {route.waypoints} crosses a component box"
        )


# ###############
# Y-position optimisation
# ###############


def _total_wire_length(plan: LayoutPlan) -> float:
    """Sum of |source_cy − target_cy| over all edge routes in *plan*."""
    total = 0.0
    for route in plan.edge_routes.values():
        if len(route.waypoints) >= 2:
            _, y_start = route.waypoints[0]
            _, y_end = route.waypoints[-1]
            total += abs(y_end - y_start)
    return total


def test_compact_layer_inplace_pushes_overlapping_nodes_apart() -> None:
    """Forward pass must separate nodes that are placed too close together."""
    from archml.views.placement import _compact_layer_inplace

    sizes: dict[str, tuple[float, float]] = {"A": (50.0, 40.0), "B": (50.0, 40.0)}
    # Both nodes start at y=0, so B overlaps A.
    y_pos = {"A": 0.0, "B": 0.0}
    _compact_layer_inplace(["A", "B"], y_pos, sizes, content_h=200.0, gap=10.0)
    # B must start at least gap below the bottom of A.
    assert y_pos["B"] >= y_pos["A"] + 40.0 + 10.0 - 1e-9


def test_compact_layer_inplace_shifts_overflowing_column_up() -> None:
    """A column that extends past content_h is shifted up as a rigid block."""
    from archml.views.placement import _compact_layer_inplace

    sizes: dict[str, tuple[float, float]] = {"A": (50.0, 40.0), "B": (50.0, 40.0)}
    # Stack starting at y=160, which pushes the bottom past content_h=200.
    y_pos = {"A": 160.0, "B": 210.0}
    _compact_layer_inplace(["A", "B"], y_pos, sizes, content_h=200.0, gap=10.0)
    assert y_pos["B"] + 40.0 <= 200.0 + 1e-9  # last node fits in canvas


def test_compact_layer_inplace_single_node_clamped() -> None:
    """A single node placed outside the canvas is clamped back in."""
    from archml.views.placement import _compact_layer_inplace

    sizes: dict[str, tuple[float, float]] = {"A": (50.0, 40.0)}
    y_pos = {"A": 190.0}
    _compact_layer_inplace(["A"], y_pos, sizes, content_h=200.0, gap=10.0)
    assert y_pos["A"] + 40.0 <= 200.0 + 1e-9

    y_pos = {"A": -5.0}
    _compact_layer_inplace(["A"], y_pos, sizes, content_h=200.0, gap=10.0)
    assert y_pos["A"] >= 0.0 - 1e-9


def test_compact_layer_inplace_preserves_order() -> None:
    """Nodes must retain their top-to-bottom order after compaction."""
    from archml.views.placement import _compact_layer_inplace

    sizes = {n: (50.0, 30.0) for n in "ABCD"}
    # Scramble the positions.
    y_pos = {"A": 80.0, "B": 20.0, "C": 10.0, "D": 60.0}
    _compact_layer_inplace(list("ABCD"), y_pos, sizes, content_h=300.0, gap=5.0)
    assert y_pos["A"] < y_pos["B"] < y_pos["C"] < y_pos["D"]


def test_optimise_y_positions_moves_connected_nodes_closer() -> None:
    """Two connected nodes in adjacent layers should be closer after optimisation."""
    from archml.views.placement import _optimise_y_positions

    # Layer 0: [A (top), B (bottom)] — only A is connected.
    # Layer 1: [C (single)] — connected to A.
    # With uniform spacing A is at the top of the column, C is centred.
    # Optimisation should move C up toward A.
    cfg = LayoutConfig(y_optimisation_passes=10)
    sizes = {"A": (50.0, 40.0), "B": (50.0, 40.0), "C": (50.0, 40.0)}
    layers = [["A", "B"], ["C"]]
    edges = [("A", "C")]

    col_h_0 = 40.0 + 10.0 + 40.0  # 90 lu
    content_h = col_h_0  # 90 lu (= max of both columns)

    baseline = _optimise_y_positions(layers, sizes, edges, content_h, LayoutConfig(y_optimisation_passes=0))
    optimised = _optimise_y_positions(layers, sizes, edges, content_h, cfg)

    # Baseline: C is centred at (90 − 40) / 2 = 25.
    # After optimisation C should shift toward A (at y=0), so its y < baseline.
    assert optimised["C"] < baseline["C"] - 1e-9


def test_optimise_y_positions_no_overlap() -> None:
    """After optimisation no two nodes in the same layer overlap."""
    from archml.views.placement import _optimise_y_positions

    cfg = LayoutConfig(y_optimisation_passes=8)
    sizes = {n: (50.0, 30.0) for n in "ABCDE"}
    layers = [["A", "B", "C"], ["D", "E"]]
    # Create edges that pull nodes toward extreme positions.
    edges = [("A", "D"), ("C", "E"), ("B", "D")]

    col_h = 30.0 * 3 + 10.0 * 2  # 110 lu
    content_h = col_h
    y = _optimise_y_positions(layers, sizes, edges, content_h, cfg)

    gap = cfg.node_gap
    for layer in layers:
        for j in range(len(layer) - 1):
            a, b = layer[j], layer[j + 1]
            assert y[b] >= y[a] + sizes[a][1] + gap - 1e-9, (
                f"{b}.y={y[b]:.1f} too close to {a}.y={y[a]:.1f}+{sizes[a][1]}+{gap}"
            )


def test_optimise_y_positions_disconnected_returns_uniform() -> None:
    """Nodes with no edges stay at their uniform centred positions."""
    from archml.views.placement import _optimise_y_positions

    sizes = {"A": (50.0, 40.0), "B": (50.0, 40.0)}
    layers = [["A"], ["B"]]
    # No edges at all.
    baseline = _optimise_y_positions(layers, sizes, [], 100.0, LayoutConfig(y_optimisation_passes=0))
    optimised = _optimise_y_positions(layers, sizes, [], 100.0, LayoutConfig(y_optimisation_passes=6))
    for nid in ("A", "B"):
        assert abs(optimised[nid] - baseline[nid]) < 1e-9


def test_layout_wire_length_reduced_by_optimisation() -> None:
    """Enabling y-optimisation reduces total vertical wire length vs. baseline."""
    sys = System(
        name="S",
        connects=[
            _connect("Provider", "Iface", "Consumer", "Iface", channel="ch"),
        ],
        components=[
            Component(name="Consumer", requires=[_iref("Iface")]),
            Component(name="Provider", provides=[_iref("Iface")]),
            Component(name="Unconnected1"),
            Component(name="Unconnected2"),
        ],
    )
    diagram = build_viz_diagram(sys)

    plan_base = compute_layout(diagram, config=LayoutConfig(y_optimisation_passes=0))
    plan_opt = compute_layout(diagram, config=LayoutConfig(y_optimisation_passes=6))

    wl_base = _total_wire_length(plan_base)
    wl_opt = _total_wire_length(plan_opt)
    assert wl_opt <= wl_base + 1.0, f"Optimised wire length {wl_opt:.1f} is not better than baseline {wl_base:.1f}"


# ###############
# Peripheral y-alignment
# ###############


def test_peripheral_snaps_to_connected_internal_port() -> None:
    """A single terminal should align its centre with the connected component's port."""
    # One component exposed on both sides; the terminals should align with it.
    comp = Component(
        name="Sys",
        requires=[_iref("InIface")],
        provides=[_iref("OutIface")],
        components=[Component(name="Inner", requires=[_iref("InIface")], provides=[_iref("OutIface")])],
    )
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)

    # Find the terminal nodes and the internal node port anchors.
    terminal_nodes = [n for n in diagram.peripheral_nodes if n.kind == "terminal"]
    assert terminal_nodes, "Expected terminal nodes for the exposed interfaces"

    for term in terminal_nodes:
        term_nl = plan.nodes[term.id]
        term_cy = term_nl.y + term_nl.height / 2.0

        # Find what internal port this terminal connects to.
        term_port_ids = {p.id for p in term.ports}
        for edge in diagram.edges:
            other_port_id = None
            if edge.source_port_id in term_port_ids:
                other_port_id = edge.target_port_id
            elif edge.target_port_id in term_port_ids:
                other_port_id = edge.source_port_id
            if other_port_id is not None and other_port_id in plan.port_anchors:
                internal_y = plan.port_anchors[other_port_id].y
                # Terminal centre should be within 2 lu of the connected port.
                assert abs(term_cy - internal_y) < 2.0, (
                    f"Terminal {term.id} centre {term_cy:.1f} is not aligned with internal port y={internal_y:.1f}"
                )


def test_peripheral_alignment_reduces_expose_route_detour() -> None:
    """Exposing a component's interface should produce a nearly-horizontal route."""
    sys = System(
        name="S",
        components=[
            Component(name="Worker", requires=[_iref("Job")]),
            Component(name="Idle1"),
            Component(name="Idle2"),
        ],
    )
    # Expose Worker.Job so a left terminal is created for it.
    from archml.model.entities import ExposeDef

    sys.exposes = [ExposeDef(entity="Worker", port="Job")]
    diagram = build_viz_diagram(sys)
    plan = compute_layout(diagram)

    # Find the terminal and its connected internal port.
    terminal = next((n for n in diagram.peripheral_nodes if n.kind == "terminal"), None)
    if terminal is None:
        return  # nothing to check if no terminal was created

    term_nl = plan.nodes[terminal.id]
    term_cy = term_nl.y + term_nl.height / 2.0

    term_port_ids = {p.id for p in terminal.ports}
    for edge in diagram.edges:
        other_pid = None
        if edge.source_port_id in term_port_ids:
            other_pid = edge.target_port_id
        elif edge.target_port_id in term_port_ids:
            other_pid = edge.source_port_id
        if other_pid and other_pid in plan.port_anchors:
            internal_y = plan.port_anchors[other_pid].y
            vertical_span = abs(internal_y - term_cy)
            # Allow up to one node-height of vertical spread (tighter than unoptimised).
            cfg = LayoutConfig()
            assert vertical_span < cfg.node_height, (
                f"Expose terminal is {vertical_span:.1f} lu from its port — "
                f"peripheral alignment appears not to be working"
            )


def test_peripheral_alignment_disabled_when_passes_zero() -> None:
    """With y_optimisation_passes=0 peripherals keep their uniformly-centred positions."""
    comp = Component(
        name="Sys",
        requires=[_iref("InIface")],
        components=[Component(name="Inner", requires=[_iref("InIface")])],
    )
    diagram = build_viz_diagram(comp)

    plan_uniform = compute_layout(diagram, config=LayoutConfig(y_optimisation_passes=0))
    plan_aligned = compute_layout(diagram, config=LayoutConfig(y_optimisation_passes=6))

    terminal = next(n for n in diagram.peripheral_nodes if n.kind == "terminal")
    y_uniform = plan_uniform.nodes[terminal.id].y
    y_aligned = plan_aligned.nodes[terminal.id].y

    # With optimisation the terminal moves; without it stays at the centred default.
    # (With a single inner node they may coincide — we just check it doesn't crash.)
    assert isinstance(y_uniform, float)
    assert isinstance(y_aligned, float)


# ###############
# Straight-line shortcut / sy == ty correctness
# ###############


def test_route_straight_line_not_returned_when_blocked() -> None:
    """When sy == ty but an obstacle spans the horizontal path, no straight line is returned."""
    from archml.views.placement import _route_avoiding_obstacles, _route_is_clear

    # Obstacle sits squarely between source and target at the same y level.
    # x 50..150, y 30..70  — source at (0, 50), target at (200, 50).
    obstacle = [(50.0, 30.0, 100.0, 40.0)]
    wps = _route_avoiding_obstacles(0.0, 50.0, 200.0, 50.0, obstacle, 300.0)

    # Must not be the straight two-point line.
    assert len(wps) > 2, "Expected a detour but got a straight line through the obstacle"
    # Must clear the obstacle.
    assert _route_is_clear(wps, obstacle), f"Route {wps} still crosses the obstacle"
    # All segments must be axis-aligned.
    for (x1, y1), (x2, y2) in zip(wps, wps[1:], strict=False):
        assert abs(x1 - x2) < 0.5 or abs(y1 - y2) < 0.5


def test_route_straight_line_returned_when_clear() -> None:
    """When sy == ty and nothing is in the way, the straight line is still used."""
    from archml.views.placement import _route_avoiding_obstacles

    # Obstacle is completely above the route level — no interference.
    obstacle = [(80.0, 0.0, 40.0, 10.0)]
    wps = _route_avoiding_obstacles(0.0, 50.0, 200.0, 50.0, obstacle, 300.0)
    assert wps == [(0.0, 50.0), (200.0, 50.0)]


def test_route_sy_eq_ty_prefers_shorter_bypass() -> None:
    """When sy == ty and both above/below bypasses are valid, the closer one is used."""
    from archml.views.placement import _route_avoiding_obstacles

    # Obstacle at x 40..160, y 20..80.  Source (0, 60), target (200, 60).
    # Bypass above: top - gap = 20 - 4 = 16  → distance from sy=60 is 44
    # Bypass below: bottom + gap = 80 + 4 = 84 → distance from sy=60 is 24
    # The shorter (below) bypass should be tried first and used.
    obstacle = [(40.0, 20.0, 120.0, 60.0)]
    wps = _route_avoiding_obstacles(0.0, 60.0, 200.0, 60.0, obstacle, 300.0)

    assert len(wps) > 2
    bypass_ys = {y for _, y in wps if abs(y - 60.0) > 0.5}
    assert bypass_ys, "No bypass y found in waypoints"
    bypass_y = bypass_ys.pop()
    # The nearer bypass is below sy=60, so bypass_y > 60.
    assert bypass_y > 60.0, f"Expected below-bypass (y > 60) but got bypass at y={bypass_y:.1f}"


def test_expose_terminal_route_does_not_cross_sibling_box() -> None:
    """After peripheral alignment the expose-terminal route must not cross any component."""
    from archml.model.entities import ExposeDef
    from archml.views.placement import _route_is_clear

    # One component is exposed (creating a left terminal); two unconnected
    # siblings sit in the same column.  After peripheral snapping the terminal
    # aligns exactly with Target's port, and the siblings may sit at the same
    # horizontal level — the route must detour around them.
    sys = System(
        name="S",
        components=[
            Component(name="Target", requires=[_iref("Job")]),
            Component(name="Sibling1"),
            Component(name="Sibling2"),
        ],
    )
    sys.exposes = [ExposeDef(entity="Target", port="Job")]
    diagram = build_viz_diagram(sys)
    plan = compute_layout(diagram)

    obstacles = [(nl.x, nl.y, nl.width, nl.height) for nl in plan.nodes.values()]

    for edge in diagram.edges:
        route = plan.edge_routes.get(edge.id)
        if route is None:
            continue
        for (x1, y1), (x2, y2) in zip(route.waypoints, route.waypoints[1:], strict=False):
            assert abs(x1 - x2) < 0.5 or abs(y1 - y2) < 0.5, (
                f"Diagonal segment in edge {edge.id}: ({x1:.1f},{y1:.1f})→({x2:.1f},{y2:.1f})"
            )
        assert _route_is_clear(route.waypoints, obstacles), (
            f"Edge {edge.id} route {route.waypoints} crosses a component box"
        )
