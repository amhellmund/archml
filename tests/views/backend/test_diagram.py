# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the SVG diagram rendering backend."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from archml.model.entities import Component, Connection, ConnectionEndpoint, InterfaceRef, System
from archml.views.backend.diagram import render_diagram
from archml.views.placement import compute_layout
from archml.views.topology import build_viz_diagram

# ###############
# Helpers
# ###############

_SVG_NS = "http://www.w3.org/2000/svg"


def _iref(name: str, version: str | None = None) -> InterfaceRef:
    return InterfaceRef(name=name, version=version)


def _conn(source: str, target: str, interface: str) -> Connection:
    return Connection(
        source=ConnectionEndpoint(entity=source),
        target=ConnectionEndpoint(entity=target),
        interface=InterfaceRef(name=interface),
    )


def _render_and_parse(entity: Component | System, tmp_path: Path, **kwargs: object) -> ET.Element:
    """Build a VizDiagram + LayoutPlan, render to SVG, and parse the result."""
    diagram = build_viz_diagram(entity)
    plan = compute_layout(diagram)
    out = tmp_path / "diagram.svg"
    render_diagram(diagram, plan, out, **kwargs)
    return ET.parse(str(out)).getroot()


def _text_content(root: ET.Element) -> list[str]:
    """Collect all non-empty text values from the SVG element tree."""
    return [el.text for el in root.iter() if el.text and el.text.strip()]


# ###############
# File creation
# ###############


def test_render_creates_svg_file(tmp_path: Path) -> None:
    """render_diagram writes a file at the specified output path."""
    comp = Component(name="Worker")
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    out = tmp_path / "out.svg"
    render_diagram(diagram, plan, out)
    assert out.exists()


def test_render_creates_parent_directory(tmp_path: Path) -> None:
    """render_diagram creates missing parent directories."""
    comp = Component(name="Worker")
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    out = tmp_path / "nested" / "deep" / "diagram.svg"
    render_diagram(diagram, plan, out)
    assert out.exists()


def test_render_output_starts_with_xml_declaration(tmp_path: Path) -> None:
    """Output file begins with an XML declaration."""
    comp = Component(name="Worker")
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    out = tmp_path / "out.svg"
    render_diagram(diagram, plan, out)
    content = out.read_text(encoding="utf-8")
    assert content.startswith("<?xml")


def test_render_output_is_valid_xml(tmp_path: Path) -> None:
    """Rendered SVG is well-formed XML."""
    comp = Component(name="SystemA", components=[Component(name="Alpha"), Component(name="Beta")])
    _render_and_parse(comp, tmp_path)  # would raise ET.ParseError if invalid


# ###############
# SVG dimensions
# ###############


def test_render_svg_width_matches_plan(tmp_path: Path) -> None:
    """SVG ``width`` attribute equals plan.total_width (with default scale=1.0)."""
    comp = Component(name="Sys", components=[Component(name="A")])
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    out = tmp_path / "out.svg"
    render_diagram(diagram, plan, out)
    root = ET.parse(str(out)).getroot()
    assert float(root.attrib["width"]) == pytest.approx(plan.total_width, rel=1e-3)


def test_render_svg_height_matches_plan(tmp_path: Path) -> None:
    """SVG ``height`` attribute equals plan.total_height (with default scale=1.0)."""
    comp = Component(name="Sys", components=[Component(name="A")])
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    out = tmp_path / "out.svg"
    render_diagram(diagram, plan, out)
    root = ET.parse(str(out)).getroot()
    assert float(root.attrib["height"]) == pytest.approx(plan.total_height, rel=1e-3)


def test_render_scale_enlarges_svg_dimensions(tmp_path: Path) -> None:
    """Applying scale > 1.0 produces a larger SVG than scale=1.0."""
    comp = Component(name="Sys", components=[Component(name="A")])
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)

    out1 = tmp_path / "s1.svg"
    out2 = tmp_path / "s2.svg"
    render_diagram(diagram, plan, out1, scale=1.0)
    render_diagram(diagram, plan, out2, scale=2.0)

    root1 = ET.parse(str(out1)).getroot()
    root2 = ET.parse(str(out2)).getroot()
    assert float(root2.attrib["width"]) > float(root1.attrib["width"])
    assert float(root2.attrib["height"]) > float(root1.attrib["height"])


# ###############
# Root boundary label
# ###############


def test_render_boundary_label_present(tmp_path: Path) -> None:
    """The root entity name appears as text in the SVG."""
    comp = Component(name="OrderService", components=[Component(name="Processor")])
    root = _render_and_parse(comp, tmp_path)
    assert "OrderService" in _text_content(root)


def test_render_boundary_label_for_system(tmp_path: Path) -> None:
    """System name appears as text in the SVG boundary."""
    sys = System(name="ECommerce", components=[Component(name="Worker")])
    root = _render_and_parse(sys, tmp_path)
    assert "ECommerce" in _text_content(root)


# ###############
# Child node labels
# ###############


def test_render_child_component_label_present(tmp_path: Path) -> None:
    """Each child component name appears as a text node in the SVG."""
    comp = Component(name="Parent", components=[Component(name="Alpha"), Component(name="Beta")])
    root = _render_and_parse(comp, tmp_path)
    texts = _text_content(root)
    assert "Alpha" in texts
    assert "Beta" in texts


def test_render_child_system_label_present(tmp_path: Path) -> None:
    """Child systems within a system appear as text nodes."""
    sys = System(
        name="Root",
        systems=[System(name="SubSys")],
        components=[Component(name="Worker")],
    )
    root = _render_and_parse(sys, tmp_path)
    texts = _text_content(root)
    assert "SubSys" in texts
    assert "Worker" in texts


def test_render_leaf_entity_produces_no_child_nodes(tmp_path: Path) -> None:
    """A leaf entity (no children) results in no child node rect elements beyond the boundary."""
    comp = Component(name="Leaf")
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    out = tmp_path / "out.svg"
    render_diagram(diagram, plan, out)
    root = ET.parse(str(out)).getroot()
    # Leaf has no child nodes in plan.nodes (only the boundary if any).
    assert len(plan.nodes) == 0
    # SVG still contains at least the boundary rect.
    rects = list(root.iter(f"{{{_SVG_NS}}}rect"))
    assert len(rects) >= 1


# ###############
# Terminal / peripheral node labels
# ###############


def test_render_requires_terminal_label_present(tmp_path: Path) -> None:
    """Requires interface terminal label appears in the SVG."""
    comp = Component(
        name="Sys",
        requires=[_iref("DataFeed")],
        components=[Component(name="A")],
    )
    root = _render_and_parse(comp, tmp_path)
    assert "DataFeed" in _text_content(root)


def test_render_provides_terminal_label_present(tmp_path: Path) -> None:
    """Provides interface terminal label appears in the SVG."""
    comp = Component(
        name="Sys",
        provides=[_iref("Result")],
        components=[Component(name="A")],
    )
    root = _render_and_parse(comp, tmp_path)
    assert "Result" in _text_content(root)


def test_render_versioned_terminal_label(tmp_path: Path) -> None:
    """Versioned interface label (e.g. ``API@v2``) appears in the SVG."""
    comp = Component(
        name="Sys",
        provides=[_iref("API", version="v2")],
        components=[Component(name="A")],
    )
    root = _render_and_parse(comp, tmp_path)
    assert "API@v2" in _text_content(root)


# ###############
# Edge labels
# ###############


def test_render_edge_label_present(tmp_path: Path) -> None:
    """Connection interface name appears as a text label in the SVG."""
    a = Component(name="A", requires=[_iref("PaymentRequest")])
    b = Component(name="B", provides=[_iref("PaymentRequest")])
    sys = System(
        name="Root",
        components=[a, b],
        connections=[_conn("A", "B", "PaymentRequest")],
    )
    root = _render_and_parse(sys, tmp_path)
    assert "PaymentRequest" in _text_content(root)


def test_render_edge_polyline_present(tmp_path: Path) -> None:
    """An edge between two children produces at least one ``<polyline>`` element."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    sys = System(
        name="Root",
        components=[a, b],
        connections=[_conn("A", "B", "IFace")],
    )
    root = _render_and_parse(sys, tmp_path)
    polylines = list(root.iter(f"{{{_SVG_NS}}}polyline"))
    assert len(polylines) >= 1


def test_render_arrowhead_marker_defined(tmp_path: Path) -> None:
    """The SVG ``<defs>`` section contains an arrowhead marker."""
    comp = Component(name="Sys", components=[Component(name="A")])
    root = _render_and_parse(comp, tmp_path)
    defs = root.find(f"{{{_SVG_NS}}}defs")
    assert defs is not None
    marker = defs.find(f"{{{_SVG_NS}}}marker")
    assert marker is not None
    assert marker.attrib.get("id") == "arrowhead"


# ###############
# Integration
# ###############


def test_render_ecommerce_system(tmp_path: Path) -> None:
    """Full integration: multi-component system with connections renders without error."""
    sys = System(
        name="ECommerce",
        components=[
            Component(name="OrderService", requires=[_iref("PaymentRequest")]),
            Component(name="PaymentService", provides=[_iref("PaymentRequest")]),
            Component(name="NotificationService", requires=[_iref("OrderRequest")]),
        ],
        connections=[
            _conn("OrderService", "PaymentService", "PaymentRequest"),
        ],
    )
    root = _render_and_parse(sys, tmp_path)
    texts = _text_content(root)
    assert "ECommerce" in texts
    assert "OrderService" in texts
    assert "PaymentService" in texts
    assert "PaymentRequest" in texts
