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
explicit filled-polygon arrowhead at the target end.

Text labels are clipped to their node bounding box via SVG ``<clipPath>``
elements, so long labels never overflow the node rectangle.

Color palette (modern, high-contrast):

- Root boundary — slate-blue fill, bold border, title label.
- Component — green tones.
- System — violet tones.
- User — amber tones.
- Channel — teal tones (communication conduit).
- External actors — slate-gray tones.
- Terminal nodes — yellow tones.
- Edges — dark navy lines with filled arrowheads.
"""

from __future__ import annotations

import math
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

# --- Modern color palette ---
# Components (green family)
_FILL_COMPONENT = "#f0fdf4"
_STROKE_COMPONENT = "#16a34a"
# Systems (violet family)
_FILL_SYSTEM = "#f5f3ff"
_STROKE_SYSTEM = "#7c3aed"
# Users (amber family)
_FILL_USER = "#fffbeb"
_STROKE_USER = "#d97706"
# Channels (teal family)
_FILL_CHANNEL = "#f0fdfa"
_STROKE_CHANNEL = "#0d9488"
# External actors (slate-gray family)
_FILL_EXTERNAL = "#f8fafc"
_STROKE_EXTERNAL = "#475569"
# Terminal interface nodes (yellow family)
_FILL_TERMINAL = "#fefce8"
_STROKE_TERMINAL = "#ca8a04"
# Root boundary (slate-blue family)
_FILL_BOUNDARY = "#eff6ff"
_STROKE_BOUNDARY = "#2563eb"
# Edges
_EDGE_COLOUR = "#1e293b"
_TEXT_COLOUR = "#1e293b"
# Diagram background
_FILL_BACKGROUND = "#ffffff"

_FONT_FAMILY = "system-ui, -apple-system, sans-serif"
_FONT_SIZE = 11
_CORNER_RADIUS = 7
_STROKE_WIDTH = 1.5
_BOUNDARY_STROKE_WIDTH = 2.0
_BOUNDARY_LABEL_OFFSET = 15.0  # y distance from boundary top to title baseline
_LABEL_PADDING = 6.0  # horizontal padding inside node for text clip region

# Channel-specific style overrides
_CHANNEL_STROKE_DASH = "5,3"  # dashed border to distinguish channels

# Arrowhead geometry (layout units, before scaling).
_ARROW_LEN = 9.0
_ARROW_HALF_W = 4.0


def _node_colours(kind: NodeKind | None) -> tuple[str, str]:
    """Return ``(fill, stroke)`` for a node kind."""
    if kind == "component":
        return _FILL_COMPONENT, _STROKE_COMPONENT
    if kind == "system":
        return _FILL_SYSTEM, _STROKE_SYSTEM
    if kind == "user":
        return _FILL_USER, _STROKE_USER
    if kind == "channel":
        return _FILL_CHANNEL, _STROKE_CHANNEL
    if kind in ("external_component", "external_system", "external_user"):
        return _FILL_EXTERNAL, _STROKE_EXTERNAL
    # terminal and unknown
    return _FILL_TERMINAL, _STROKE_TERMINAL


def _f(value: float, scale: float) -> str:
    """Format *value* scaled to two decimal places as a string."""
    return f"{value * scale:.2f}"


def _make_clip_id(node_id: str) -> str:
    """Return a safe XML ID for the ``<clipPath>`` of *node_id*."""
    safe = node_id.replace(".", "-").replace(":", "-").replace("/", "-").replace("@", "-")
    return f"clip-{safe}"


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

    # White background rectangle.
    ET.SubElement(
        svg,
        "rect",
        {
            "x": "0",
            "y": "0",
            "width": f"{tw:.2f}",
            "height": f"{th:.2f}",
            "fill": _FILL_BACKGROUND,
        },
    )

    defs = ET.SubElement(svg, "defs")

    # Root boundary
    if diagram.root.id in plan.boundaries:
        _render_boundary(svg, diagram.root.label, plan.boundaries[diagram.root.id], scale)

    # Build a metadata map: node_id → (label, title, kind) for all renderable nodes.
    node_meta: dict[str, tuple[str, str | None, NodeKind | None]] = {}
    for child in diagram.root.children:
        if isinstance(child, VizNode):
            node_meta[child.id] = (child.label, child.title, child.kind)
    for node in diagram.peripheral_nodes:
        node_meta[node.id] = (node.label, node.title, node.kind)

    # Render all positioned nodes (clip paths added to <defs>).
    for node_id, nl in plan.nodes.items():
        label, title, kind = node_meta.get(node_id, (node_id, None, None))
        clip_id = _make_clip_id(node_id)
        _add_node_clip(defs, clip_id, nl, scale)
        _render_node(svg, label, title, nl, kind, scale, clip_id)

    # Render edges with explicit arrowheads.
    for edge in diagram.edges:
        route = plan.edge_routes.get(edge.id)
        if route is not None:
            _render_edge(svg, route.waypoints, edge.label, scale)

    return svg


def _add_node_clip(defs: ET.Element, clip_id: str, nl: NodeLayout, scale: float) -> None:
    """Add a ``<clipPath>`` for *nl* to *defs*, using the node bounds with padding."""
    clip = ET.SubElement(defs, "clipPath", {"id": clip_id})
    ET.SubElement(
        clip,
        "rect",
        {
            "x": _f(nl.x + _LABEL_PADDING, scale),
            "y": _f(nl.y, scale),
            "width": _f(nl.width - 2 * _LABEL_PADDING, scale),
            "height": _f(nl.height, scale),
        },
    )


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
    title: str | None,
    nl: NodeLayout,
    kind: NodeKind | None,
    scale: float,
    clip_id: str,
) -> None:
    """Draw a node rectangle with a centred, clipped label.

    For channel nodes, renders two lines: the interface name (larger) above
    centre and the channel name (smaller) below centre.
    """
    fill, stroke = _node_colours(kind)
    r = str(_CORNER_RADIUS)

    rect_attrs: dict[str, str] = {
        "x": _f(nl.x, scale),
        "y": _f(nl.y, scale),
        "width": _f(nl.width, scale),
        "height": _f(nl.height, scale),
        "rx": r,
        "ry": r,
        "fill": fill,
        "stroke": stroke,
        "stroke-width": str(_STROKE_WIDTH),
    }
    if kind == "channel":
        rect_attrs["stroke-dasharray"] = _CHANNEL_STROKE_DASH

    ET.SubElement(svg, "rect", rect_attrs)

    cx = _f(nl.x + nl.width / 2, scale)
    cy_mid = nl.y + nl.height / 2

    if kind == "channel":
        # Two-line layout: interface name (larger) above centre, channel name below.
        iface_name = title if title is not None else label
        line_gap = _FONT_SIZE * scale * 0.7
        text_top = ET.SubElement(
            svg,
            "text",
            {
                "x": cx,
                "y": _f(cy_mid - line_gap * 0.5, scale),
                "text-anchor": "middle",
                "dominant-baseline": "middle",
                "font-family": _FONT_FAMILY,
                "font-size": str(int(_FONT_SIZE * scale)),
                "fill": _TEXT_COLOUR,
                "clip-path": f"url(#{clip_id})",
            },
        )
        text_top.text = iface_name
        text_bot = ET.SubElement(
            svg,
            "text",
            {
                "x": cx,
                "y": _f(cy_mid + line_gap * 0.9, scale),
                "text-anchor": "middle",
                "dominant-baseline": "middle",
                "font-family": _FONT_FAMILY,
                "font-size": str(int(_FONT_SIZE * scale * 0.75)),
                "fill": _TEXT_COLOUR,
                "clip-path": f"url(#{clip_id})",
            },
        )
        text_bot.text = f"${label}"
    else:
        text = ET.SubElement(
            svg,
            "text",
            {
                "x": cx,
                "y": _f(cy_mid, scale),
                "text-anchor": "middle",
                "dominant-baseline": "middle",
                "font-family": _FONT_FAMILY,
                "font-size": str(int(_FONT_SIZE * scale)),
                "fill": _TEXT_COLOUR,
                "clip-path": f"url(#{clip_id})",
            },
        )
        text.text = label


def _render_edge(
    svg: ET.Element,
    waypoints: list[tuple[float, float]],
    label: str,
    scale: float,
) -> None:
    """Draw an edge as a polyline body plus an explicit arrowhead polygon at the target end."""
    if len(waypoints) < 2:
        return

    # Compute the arrowhead direction from the last segment of the edge.
    x1, y1 = waypoints[-2]
    x2, y2 = waypoints[-1]
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return

    ndx, ndy = dx / length, dy / length

    # The arrow tip is at the target port anchor; the base is set back by _ARROW_LEN.
    arrow_len = min(_ARROW_LEN, length * 0.45)
    base_x = x2 - arrow_len * ndx
    base_y = y2 - arrow_len * ndy

    # Edge body: polyline stopping at the arrowhead base so it doesn't overlap it.
    body_wps = list(waypoints[:-1]) + [(base_x, base_y)]
    points_str = " ".join(f"{x * scale:.2f},{y * scale:.2f}" for x, y in body_wps)
    ET.SubElement(
        svg,
        "polyline",
        {
            "points": points_str,
            "fill": "none",
            "stroke": _EDGE_COLOUR,
            "stroke-width": "1.5",
            "stroke-linejoin": "round",
            "stroke-linecap": "round",
        },
    )

    # Arrowhead: filled triangle (tip, left wing, right wing).
    lx = base_x - _ARROW_HALF_W * ndy
    ly = base_y + _ARROW_HALF_W * ndx
    rx_pt = base_x + _ARROW_HALF_W * ndy
    ry_pt = base_y - _ARROW_HALF_W * ndx
    arrow_pts = " ".join(f"{x * scale:.2f},{y * scale:.2f}" for x, y in [(x2, y2), (lx, ly), (rx_pt, ry_pt)])
    ET.SubElement(svg, "polygon", {"points": arrow_pts, "fill": _EDGE_COLOUR})

    # Label at the midpoint of the edge.
    mid = len(waypoints) // 2
    mx = (waypoints[mid - 1][0] + waypoints[mid][0]) / 2 * scale
    my = (waypoints[mid - 1][1] + waypoints[mid][1]) / 2 * scale - 4 * scale
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
