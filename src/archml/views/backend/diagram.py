# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""SVG diagram backend for ArchML architecture views.

Renders a :class:`~archml.views.topology.VizDiagram` using the pre-computed
:class:`~archml.views.placement.LayoutPlan` geometry, producing a standalone
SVG file.

All coordinates are taken directly from the layout plan — no additional layout
engine is involved.  Each :class:`~archml.views.placement.NodeLayout` maps to
a styled ``<rect>``/``<text>`` pair, each
:class:`~archml.views.placement.BoundaryLayout` to a labelled rectangle, and
each :class:`~archml.views.placement.EdgeRoute` to a ``<polyline>`` with an
arrowhead at the target end.

The visual vocabulary mirrors the colour scheme used by the original
``diagrams``-based renderer:

- Root boundary — light blue fill, bold-blue border, title label.
- Internal child nodes — green (component) or blue (system).
- External actor nodes — purple.
- Terminal nodes — amber.
- Edges — dark-grey polylines with a filled arrowhead and a midpoint label.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from archml.views.placement import BoundaryLayout, LayoutPlan, NodeLayout
from archml.views.topology import NodeKind, VizDiagram, VizNode

# ###############
# Public Interface
# ###############


def render_diagram(
    diagram: VizDiagram,
    plan: LayoutPlan,
    output_path: Path,
    *,
    scale: float = 1.0,
) -> None:
    """Render *diagram* to an SVG file at *output_path*.

    Uses the geometry recorded in *plan* to position every element.  All
    layout-unit coordinates are multiplied by *scale* to obtain SVG user units
    (at 96 dpi, 1 layout unit ≈ 1 px by default).

    The output directory is created automatically if it does not exist.

    Args:
        diagram: The topology to render, as produced by
            :func:`~archml.views.topology.build_viz_diagram`.
        plan: The pre-computed layout plan produced by
            :func:`~archml.views.placement.compute_layout`.
        output_path: Destination path for the SVG file.
        scale: Multiplier applied to all layout-unit coordinates.
            Defaults to ``1.0``.
    """
    svg = _build_svg(diagram, plan, scale)
    _write_svg(svg, output_path)


# ################
# Implementation
# ################

# --- Colour palette (matches original diagrams-based renderer) ---
_FILL_COMPONENT = "#e8f4e8"
_STROKE_COMPONENT = "#448844"
_FILL_SYSTEM = "#ddeeff"
_STROKE_SYSTEM = "#4466aa"
_FILL_EXTERNAL = "#f0e8f0"
_STROKE_EXTERNAL = "#664488"
_FILL_TERMINAL = "#fff8e1"
_STROKE_TERMINAL = "#aa8833"
_FILL_BOUNDARY = "#eef4ff"
_STROKE_BOUNDARY = "#4466aa"
_EDGE_COLOUR = "#444444"
_TEXT_COLOUR = "#222222"

_FONT_FAMILY = "sans-serif"
_FONT_SIZE = 11
_CORNER_RADIUS = 6
_STROKE_WIDTH = 1.5
_BOUNDARY_STROKE_WIDTH = 2.0
_BOUNDARY_LABEL_OFFSET = 14.0  # y offset of boundary title from top edge


def _node_colours(kind: NodeKind | None) -> tuple[str, str]:
    """Return ``(fill, stroke)`` for a node kind."""
    if kind == "component":
        return _FILL_COMPONENT, _STROKE_COMPONENT
    if kind == "system":
        return _FILL_SYSTEM, _STROKE_SYSTEM
    if kind in ("external_component", "external_system"):
        return _FILL_EXTERNAL, _STROKE_EXTERNAL
    return _FILL_TERMINAL, _STROKE_TERMINAL


def _f(value: float, scale: float) -> str:
    """Format *value* scaled to two decimal places as a string."""
    return f"{value * scale:.2f}"


def _build_svg(diagram: VizDiagram, plan: LayoutPlan, scale: float) -> ET.Element:
    """Construct the complete SVG element tree from *diagram* and *plan*."""
    tw = plan.total_width * scale
    th = plan.total_height * scale

    svg = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": f"0 0 {tw:.2f} {th:.2f}",
            "width": f"{tw:.2f}",
            "height": f"{th:.2f}",
        },
    )

    _add_defs(svg)

    # Root boundary
    if diagram.root.id in plan.boundaries:
        _render_boundary(svg, diagram.root.label, plan.boundaries[diagram.root.id], scale)

    # Build a metadata map: node_id → (label, kind) for all renderable nodes.
    node_meta: dict[str, tuple[str, NodeKind | None]] = {}
    for child in diagram.root.children:
        if isinstance(child, VizNode):
            node_meta[child.id] = (child.label, child.kind)
    for node in diagram.peripheral_nodes:
        node_meta[node.id] = (node.label, node.kind)

    # Render all positioned nodes.
    for node_id, nl in plan.nodes.items():
        label, kind = node_meta.get(node_id, (node_id, None))
        _render_node(svg, label, nl, kind, scale)

    # Render edges.
    for edge in diagram.edges:
        route = plan.edge_routes.get(edge.id)
        if route is not None:
            _render_edge(svg, route.waypoints, edge.label, scale)

    return svg


def _add_defs(svg: ET.Element) -> None:
    """Add a ``<defs>`` block containing the arrowhead marker."""
    defs = ET.SubElement(svg, "defs")
    marker = ET.SubElement(
        defs,
        "marker",
        {
            "id": "arrowhead",
            "markerWidth": "8",
            "markerHeight": "6",
            "refX": "7",
            "refY": "3",
            "orient": "auto",
        },
    )
    ET.SubElement(marker, "polygon", {"points": "0 0, 8 3, 0 6", "fill": _EDGE_COLOUR})


def _render_boundary(svg: ET.Element, label: str, bl: BoundaryLayout, scale: float) -> None:
    """Draw the root boundary rectangle with a title label."""
    r = str(_CORNER_RADIUS)
    ET.SubElement(
        svg,
        "rect",
        {
            "x": _f(bl.x, scale),
            "y": _f(bl.y, scale),
            "width": _f(bl.width, scale),
            "height": _f(bl.height, scale),
            "rx": r,
            "ry": r,
            "fill": _FILL_BOUNDARY,
            "stroke": _STROKE_BOUNDARY,
            "stroke-width": str(_BOUNDARY_STROKE_WIDTH),
        },
    )
    title = ET.SubElement(
        svg,
        "text",
        {
            "x": _f(bl.x + bl.width / 2, scale),
            "y": _f(bl.y + _BOUNDARY_LABEL_OFFSET, scale),
            "text-anchor": "middle",
            "dominant-baseline": "middle",
            "font-family": _FONT_FAMILY,
            "font-size": str(int(_FONT_SIZE * scale * 1.1)),
            "font-weight": "bold",
            "fill": _STROKE_BOUNDARY,
        },
    )
    title.text = label


def _render_node(
    svg: ET.Element,
    label: str,
    nl: NodeLayout,
    kind: NodeKind | None,
    scale: float,
) -> None:
    """Draw a node rectangle with a centred label."""
    fill, stroke = _node_colours(kind)
    r = str(_CORNER_RADIUS)
    ET.SubElement(
        svg,
        "rect",
        {
            "x": _f(nl.x, scale),
            "y": _f(nl.y, scale),
            "width": _f(nl.width, scale),
            "height": _f(nl.height, scale),
            "rx": r,
            "ry": r,
            "fill": fill,
            "stroke": stroke,
            "stroke-width": str(_STROKE_WIDTH),
        },
    )
    text = ET.SubElement(
        svg,
        "text",
        {
            "x": _f(nl.x + nl.width / 2, scale),
            "y": _f(nl.y + nl.height / 2, scale),
            "text-anchor": "middle",
            "dominant-baseline": "middle",
            "font-family": _FONT_FAMILY,
            "font-size": str(int(_FONT_SIZE * scale)),
            "fill": _TEXT_COLOUR,
        },
    )
    text.text = label


def _render_edge(
    svg: ET.Element,
    waypoints: list[tuple[float, float]],
    label: str,
    scale: float,
) -> None:
    """Draw a polyline edge with an arrowhead and a midpoint label."""
    if len(waypoints) < 2:
        return

    points_str = " ".join(f"{x * scale:.2f},{y * scale:.2f}" for x, y in waypoints)
    ET.SubElement(
        svg,
        "polyline",
        {
            "points": points_str,
            "fill": "none",
            "stroke": _EDGE_COLOUR,
            "stroke-width": "1.2",
            "marker-end": "url(#arrowhead)",
        },
    )

    # Label at the midpoint of the edge.
    mid = len(waypoints) // 2
    x1, y1 = waypoints[mid - 1]
    x2, y2 = waypoints[mid]
    mx = (x1 + x2) / 2 * scale
    my = (y1 + y2) / 2 * scale - 4 * scale

    text = ET.SubElement(
        svg,
        "text",
        {
            "x": f"{mx:.2f}",
            "y": f"{my:.2f}",
            "text-anchor": "middle",
            "font-family": _FONT_FAMILY,
            "font-size": str(int(_FONT_SIZE * scale * 0.9)),
            "fill": _EDGE_COLOUR,
        },
    )
    text.text = label


def _write_svg(svg: ET.Element, output_path: Path) -> None:
    """Write *svg* to *output_path* as a UTF-8 SVG file with XML declaration."""
    ET.indent(svg, space="  ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(svg)
    with output_path.open("w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="utf-8"?>\n')
        tree.write(fh, encoding="unicode", xml_declaration=False)
