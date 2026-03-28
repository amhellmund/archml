# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the SVG diagram rendering backend."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from archml.model.entities import Component, ConnectDef, ExposeDef, InterfaceRef, System
from archml.views.diagram import render_diagram
from archml.views.layout import compute_layout
from archml.views.topology import build_viz_diagram

# ###############
# Helpers
# ###############

_SVG_NS = "http://www.w3.org/2000/svg"


def _iref(name: str) -> InterfaceRef:
    return InterfaceRef(name=name)


def _connect(src_entity: str, src_port: str, dst_entity: str, dst_port: str, channel: str | None = None) -> ConnectDef:
    return ConnectDef(
        src_entity=src_entity, src_port=src_port, channel=channel, dst_entity=dst_entity, dst_port=dst_port
    )


def _expose(entity: str, port: str, as_name: str | None = None) -> ExposeDef:
    return ExposeDef(entity=entity, port=port, as_name=as_name)


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
    """The root boundary box is drawn with its label and child node labels also appear."""
    comp = Component(name="OrderService", components=[Component(name="Processor")])
    root = _render_and_parse(comp, tmp_path)
    texts = _text_content(root)
    assert "OrderService" in texts
    assert "Processor" in texts


def test_render_boundary_label_for_system(tmp_path: Path) -> None:
    """System root boundary is drawn; both the system name and child labels appear."""
    sys = System(name="ECommerce", components=[Component(name="Worker")])
    root = _render_and_parse(sys, tmp_path)
    texts = _text_content(root)
    assert "ECommerce" in texts
    assert "Worker" in texts


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


def test_render_variant_terminal_label(tmp_path: Path) -> None:
    """Interface with a variant annotation still renders by its plain name."""
    comp = Component(
        name="Sys",
        provides=[_iref("API")],
        components=[Component(name="A")],
    )
    root = _render_and_parse(comp, tmp_path)
    assert "API" in _text_content(root)


# ###############
# Edge labels
# ###############


def test_render_edge_label_present(tmp_path: Path) -> None:
    """Connect interface name appears as a text label in the SVG."""
    a = Component(name="A", requires=[_iref("PaymentRequest")])
    b = Component(name="B", provides=[_iref("PaymentRequest")])
    sys = System(
        name="Root",
        connects=[_connect("B", "PaymentRequest", "A", "PaymentRequest", channel="payment")],
        components=[a, b],
    )
    root = _render_and_parse(sys, tmp_path)
    assert "PaymentRequest" in _text_content(root)


def test_render_node_text_has_clip_path(tmp_path: Path) -> None:
    """Each node text element references a clip-path to prevent label overflow."""
    comp = Component(name="Sys", components=[Component(name="LongComponentNameThatMightOverflow")])
    root = _render_and_parse(comp, tmp_path)
    texts = [el for el in root.iter(f"{{{_SVG_NS}}}text") if "clip-path" in el.attrib]
    assert len(texts) >= 1


def test_render_clip_paths_defined_in_defs(tmp_path: Path) -> None:
    """``<clipPath>`` elements for node labels are defined inside ``<defs>``."""
    comp = Component(name="Sys", components=[Component(name="A"), Component(name="B")])
    root = _render_and_parse(comp, tmp_path)
    defs = root.find(f"{{{_SVG_NS}}}defs")
    assert defs is not None
    clip_paths = list(defs.iter(f"{{{_SVG_NS}}}clipPath"))
    assert len(clip_paths) >= 2  # one per child node


def test_render_edge_polyline_present(tmp_path: Path) -> None:
    """An edge between two children produces at least one ``<polyline>`` element."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    sys = System(
        name="Root",
        connects=[_connect("B", "IFace", "A", "IFace", channel="ch")],
        components=[a, b],
    )
    root = _render_and_parse(sys, tmp_path)
    polylines = list(root.iter(f"{{{_SVG_NS}}}polyline"))
    assert len(polylines) >= 1


def test_render_edge_has_explicit_arrowhead_polygon(tmp_path: Path) -> None:
    """An edge produces an explicit filled ``<polygon>`` arrowhead in the SVG."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    sys = System(
        name="Root",
        connects=[_connect("B", "IFace", "A", "IFace", channel="ch")],
        components=[a, b],
    )
    root = _render_and_parse(sys, tmp_path)
    polygons = list(root.iter(f"{{{_SVG_NS}}}polygon"))
    assert len(polygons) >= 1
    # The arrowhead polygon uses the CSS class (no inline fill).
    classes = {p.attrib.get("class") for p in polygons}
    assert any(c == "archml-arrowhead" for c in classes)


# ###############
# Integration
# ###############


def test_render_ecommerce_system(tmp_path: Path) -> None:
    """Full integration: multi-component system with connect renders without error."""
    sys = System(
        name="ECommerce",
        connects=[_connect("PaymentService", "PaymentRequest", "OrderService", "PaymentRequest", channel="payment")],
        components=[
            Component(name="OrderService", requires=[_iref("PaymentRequest")]),
            Component(name="PaymentService", provides=[_iref("PaymentRequest")]),
            Component(name="NotificationService", requires=[_iref("OrderRequest")]),
        ],
    )
    root = _render_and_parse(sys, tmp_path)
    texts = _text_content(root)
    # Root entity boundary is drawn — "ECommerce" label appears alongside children.
    assert "ECommerce" in texts
    assert "OrderService" in texts
    assert "PaymentService" in texts
    assert "PaymentRequest" in texts


# ###############
# Root boundary box
# ###############


def test_render_root_boundary_box_present_for_component(tmp_path: Path) -> None:
    """When visualising a specific component, its boundary rect is drawn."""
    comp = Component(name="Worker", components=[Component(name="Task")])
    root = _render_and_parse(comp, tmp_path)
    # At least 3 rects: background + root boundary + child node.
    rects = list(root.iter(f"{{{_SVG_NS}}}rect"))
    assert len(rects) >= 3


def test_render_root_boundary_box_present_for_system(tmp_path: Path) -> None:
    """When visualising a specific system, its boundary rect is drawn."""
    sys = System(name="MySystem", components=[Component(name="A")])
    root = _render_and_parse(sys, tmp_path)
    texts = _text_content(root)
    assert "MySystem" in texts


# ###############
# Expose-based terminals
# ###############


def test_render_expose_requires_terminal_present(tmp_path: Path) -> None:
    """Expose of a child requires port creates a terminal label outside the boundary."""
    sub = Component(name="Sub", requires=[_iref("DataFeed")])
    comp = Component(
        name="Parent",
        components=[sub],
        exposes=[_expose("Sub", "DataFeed")],
    )
    root = _render_and_parse(comp, tmp_path)
    assert "DataFeed" in _text_content(root)


def test_render_expose_provides_terminal_present(tmp_path: Path) -> None:
    """Expose of a child provides port creates a terminal label outside the boundary."""
    sub = Component(name="Sub", provides=[_iref("Result")])
    comp = Component(
        name="Parent",
        components=[sub],
        exposes=[_expose("Sub", "Result")],
    )
    root = _render_and_parse(comp, tmp_path)
    assert "Result" in _text_content(root)


# ###############
# CSS class usage
# ###############


def test_render_node_rects_have_css_class(tmp_path: Path) -> None:
    """Node rects carry an ``archml-node`` CSS class and presentation-attribute fallbacks."""
    comp = Component(name="Parent", components=[Component(name="Alpha"), Component(name="Beta")])
    root = _render_and_parse(comp, tmp_path)
    node_rects = [r for r in root.iter(f"{{{_SVG_NS}}}rect") if "archml-node" in (r.attrib.get("class") or "")]
    assert len(node_rects) >= 2
    # CSS class is present for CSS-capable viewers.
    for rect in node_rects:
        assert "archml-node" in rect.attrib.get("class", "")
    # Presentation-attribute fallbacks are also set so non-CSS viewers get colour.
    for rect in node_rects:
        assert rect.attrib.get("fill")
        assert rect.attrib.get("stroke")


def test_render_svg_contains_embedded_css(tmp_path: Path) -> None:
    """Rendered SVG contains a ``<style>`` element with ``archml-`` CSS content."""
    comp = Component(name="Sys", components=[Component(name="A")])
    root = _render_and_parse(comp, tmp_path)
    styles = list(root.iter(f"{{{_SVG_NS}}}style"))
    assert len(styles) >= 1
    css_text = styles[0].text or ""
    assert "archml-" in css_text


def test_render_edge_polyline_has_css_class(tmp_path: Path) -> None:
    """Edge polylines carry the ``archml-edge`` CSS class and presentation-attribute fallbacks."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    sys = System(
        name="Root",
        connects=[_connect("B", "IFace", "A", "IFace", channel="ch")],
        components=[a, b],
    )
    root = _render_and_parse(sys, tmp_path)
    polylines = list(root.iter(f"{{{_SVG_NS}}}polyline"))
    assert len(polylines) >= 1
    for pl in polylines:
        assert pl.attrib.get("class") == "archml-edge"
        assert pl.attrib.get("stroke")  # fallback stroke colour is set


def test_render_expose_terminals_produce_peripheral_nodes(tmp_path: Path) -> None:
    """Exposed ports produce peripheral nodes that cause edges to be drawn."""
    sub1 = Component(name="SubA1", requires=[_iref("OrderRequest")], provides=[_iref("AInternal")])
    sub2 = Component(name="SubA2", requires=[_iref("AInternal")], provides=[_iref("Simple")])
    comp = Component(
        name="A",
        components=[sub1, sub2],
        connects=[_connect("SubA1", "AInternal", "SubA2", "AInternal", channel="internal_a")],
        exposes=[_expose("SubA1", "OrderRequest"), _expose("SubA2", "Simple")],
    )
    root = _render_and_parse(comp, tmp_path)
    texts = _text_content(root)
    # Root boundary label present.
    assert "A" in texts
    # Child nodes present.
    assert "SubA1" in texts
    assert "SubA2" in texts
    # Expose-based terminal labels present.
    assert "OrderRequest" in texts
    assert "Simple" in texts
    # At least one edge (polyline) drawn.
    polylines = list(root.iter(f"{{{_SVG_NS}}}polyline"))
    assert len(polylines) >= 1
