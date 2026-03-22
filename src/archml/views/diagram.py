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

Color palette:

- Root boundary — no box drawn (top-level architecture is not framed).
- Component — orange tones.
- System — blue tones.
- User — amber tones.
- Channel / interface / terminal — red tones, dashed border.
- External actors — slate-gray tones.
- Edges — dark navy lines with filled arrowheads.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

from archml.views.placement import BoundaryLayout, LayoutPlan, NodeLayout
from archml.views.topology import BoundaryKind, NodeKind, VizBoundary, VizDiagram, VizNode

# Mapping: topology id → (entity_path, kind_str)
_EntityInfoMap = dict[str, tuple[str, str]]

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


def render_diagram_to_svg_string(
    diagram: VizDiagram,
    plan: LayoutPlan,
    *,
    scale: float = 1.0,
) -> str:
    """Render *diagram* to an SVG string with interactive ``data-entity-path`` attributes.

    Returns the SVG markup as a Unicode string (no XML declaration) suitable
    for inline embedding in HTML.  Nodes and boundaries that correspond to
    named architecture entities carry ``data-entity-path`` and
    ``data-entity-kind`` attributes and the CSS class ``archml-entity`` so
    that a JavaScript frontend can identify click targets.

    Args:
        diagram: The topology to render.
        plan: The pre-computed layout plan.
        scale: Coordinate multiplier (default 1.0).

    Returns:
        The SVG document as a Unicode string without an XML declaration.
    """
    entity_info = _collect_entity_info(diagram)
    svg = _build_svg_interactive(diagram, plan, scale, entity_info)
    ET.indent(svg, space="  ")
    return ET.tostring(svg, encoding="unicode")


# ################
# Implementation
# ################

# --- Color palette ---
# Components (orange family)
_FILL_COMPONENT = "#fff7ed"
_STROKE_COMPONENT = "#ea580c"
# Systems (blue family)
_FILL_SYSTEM = "#eff6ff"
_STROKE_SYSTEM = "#2563eb"
# Users (amber family)
_FILL_USER = "#fffbeb"
_STROKE_USER = "#d97706"
# Channels / interfaces (red family, dashed border)
_FILL_CHANNEL = "#fef2f2"
_STROKE_CHANNEL = "#dc2626"
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
_FONT_SIZE = 15
_CORNER_RADIUS = 7
_STROKE_WIDTH = 1.5
_BOUNDARY_STROKE_WIDTH = 2.0
_BOUNDARY_LABEL_OFFSET = 21.0  # y distance from boundary top to title baseline
_LABEL_PADDING = 6.0  # horizontal padding inside node for text clip region

# Channel / interface node layout — must match LayoutConfig defaults.
_CHANNEL_STROKE_DASH = "5,3"
_CHANNEL_LINE_GAP = 8.0  # explicit gap (layout units) between the two text lines
_CHANNEL_LABEL_FONT_RATIO = 0.9  # channel-label font size relative to interface-name font size

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
    if kind in ("channel", "interface", "terminal"):
        return _FILL_CHANNEL, _STROKE_CHANNEL
    if kind in ("external_component", "external_system", "external_user"):
        return _FILL_EXTERNAL, _STROKE_EXTERNAL
    # unknown
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

    # Root boundary — draw a box for real entities; skip only the synthetic
    # "all" diagram whose root is labelled "Architecture" and has id "all".
    if diagram.root.id != "all":
        root_bl = plan.boundaries.get(diagram.root.id)
        if root_bl is not None:
            _render_boundary(svg, diagram.root.label, root_bl, scale, kind=diagram.root.kind)

    # Nested boundaries (expanded sub-systems/components) — rendered outermost-first so
    # inner boundaries appear on top.  Collect them in BFS order.
    nested: list[VizBoundary] = []
    _collect_nested_boundaries(diagram.root, nested)
    for bnd in nested:
        if bnd.id in plan.boundaries:
            _render_boundary(svg, bnd.label, plan.boundaries[bnd.id], scale, kind=bnd.kind)

    # Build a metadata map: node_id → (label, title, kind) for all renderable nodes.
    node_meta: dict[str, tuple[str, str | None, NodeKind | None]] = {}
    _collect_node_meta(diagram.root, node_meta)
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


def _collect_nested_boundaries(boundary: VizBoundary, result: list[VizBoundary]) -> None:
    """Append all nested VizBoundary children to *result* in BFS order (outermost first)."""
    for child in boundary.children:
        if isinstance(child, VizBoundary):
            result.append(child)
            _collect_nested_boundaries(child, result)


def _collect_node_meta(
    boundary: VizBoundary,
    result: dict[str, tuple[str, str | None, NodeKind | None]],
) -> None:
    """Recursively collect node metadata from all leaf VizNodes in *boundary*."""
    for child in boundary.children:
        if isinstance(child, VizNode):
            result[child.id] = (child.label, child.title, child.kind)
        elif isinstance(child, VizBoundary):
            _collect_node_meta(child, result)


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


def _render_boundary(
    svg: ET.Element,
    label: str,
    bl: BoundaryLayout,
    scale: float,
    *,
    kind: BoundaryKind | None = None,
) -> None:
    """Draw a boundary rectangle with a title label.

    *kind* selects the colour palette: ``"component"`` uses orange tones,
    ``"system"`` uses blue tones.  ``None`` (the default) falls back to the
    blue boundary palette.
    """
    if kind == "component":
        fill, stroke = _FILL_COMPONENT, _STROKE_COMPONENT
    elif kind == "system":
        fill, stroke = _FILL_SYSTEM, _STROKE_SYSTEM
    else:
        fill, stroke = _FILL_BOUNDARY, _STROKE_BOUNDARY
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
            "fill": fill,
            "stroke": stroke,
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
            "fill": stroke,
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
    if kind in ("channel", "interface", "terminal"):
        rect_attrs["stroke-dasharray"] = _CHANNEL_STROKE_DASH

    ET.SubElement(svg, "rect", rect_attrs)

    cx = _f(nl.x + nl.width / 2, scale)
    cy_mid = nl.y + nl.height / 2

    if kind == "channel" or kind in ("terminal", "interface"):
        # Two-line layout: bold interface name above, smaller italic secondary label below.
        # For channel nodes: top = title (interface name), bottom = $label (channel name).
        # For terminal/interface nodes: top = label (interface name),
        #   bottom = $title (channel name) when known, otherwise "exposed".
        if kind == "channel":
            iface_name = title if title is not None else label
            secondary = f"${label}"
        else:
            iface_name = label
            secondary = f"${title}" if title is not None else "exposed"
        fs = _FONT_SIZE
        fs_small = _FONT_SIZE * _CHANNEL_LABEL_FONT_RATIO
        gap = _CHANNEL_LINE_GAP
        # Centre the content block (line1 + gap + line2) around cy_mid.
        # With dominant-baseline="middle" the y coordinate is the visual line centre.
        line1_y = cy_mid - (fs_small + gap) / 2
        line2_y = cy_mid + (fs + gap) / 2
        text_top = ET.SubElement(
            svg,
            "text",
            {
                "x": cx,
                "y": _f(line1_y, scale),
                "text-anchor": "middle",
                "dominant-baseline": "middle",
                "font-family": _FONT_FAMILY,
                "font-size": str(int(fs * scale)),
                "font-weight": "bold",
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
                "y": _f(line2_y, scale),
                "text-anchor": "middle",
                "dominant-baseline": "middle",
                "font-family": _FONT_FAMILY,
                "font-size": str(int(fs_small * scale)),
                "font-style": "italic",
                "fill": _TEXT_COLOUR,
                "clip-path": f"url(#{clip_id})",
            },
        )
        text_bot.text = secondary
    else:
        text_attrs: dict[str, str] = {
            "x": cx,
            "y": _f(cy_mid, scale),
            "text-anchor": "middle",
            "dominant-baseline": "middle",
            "font-family": _FONT_FAMILY,
            "font-size": str(int(_FONT_SIZE * scale)),
            "fill": _TEXT_COLOUR,
            "clip-path": f"url(#{clip_id})",
        }
        if kind in ("component", "system", "interface", "terminal"):
            text_attrs["font-weight"] = "bold"
        text = ET.SubElement(svg, "text", text_attrs)
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


def _write_svg(svg: ET.Element, output_path: Path) -> None:
    """Write *svg* to *output_path* as a UTF-8 SVG file with XML declaration."""
    ET.indent(svg, space="  ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(svg)
    with output_path.open("w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="utf-8"?>\n')
        tree.write(fh, encoding="unicode", xml_declaration=False)


def _collect_entity_info(diagram: VizDiagram) -> _EntityInfoMap:
    """Build a mapping from topology ID to (entity_path, kind_str) for every element.

    For terminal nodes (which carry ``entity_path=""`` in the topology), the
    interface name (``node.label``) is used as the entity_path so that they
    are still reachable as click targets.
    """
    result: _EntityInfoMap = {}
    _walk_boundary_info(diagram.root, result)
    for node in diagram.peripheral_nodes:
        if node.entity_path:
            result[node.id] = (node.entity_path, node.kind)
        elif node.kind in ("terminal", "interface") and node.label:
            # Use the interface name as a stand-in entity_path for click routing.
            result[node.id] = (node.label, node.kind)
    return result


def _walk_boundary_info(boundary: VizBoundary, result: _EntityInfoMap) -> None:
    """Recursively collect entity info from a boundary and its children."""
    if boundary.entity_path:
        result[boundary.id] = (boundary.entity_path, boundary.kind)
    for child in boundary.children:
        if isinstance(child, VizNode):
            if child.entity_path:
                result[child.id] = (child.entity_path, child.kind)
            elif child.kind == "channel" and child.label:
                # Channel nodes have no entity_path; use the interface name (title)
                # so the sidebar can look up and display the interface definition.
                result[child.id] = (child.title or child.label, child.kind)
        else:
            _walk_boundary_info(child, result)


def _build_svg_interactive(
    diagram: VizDiagram,
    plan: LayoutPlan,
    scale: float,
    entity_info: _EntityInfoMap,
) -> ET.Element:
    """Build SVG element tree with ``archml-entity`` group wrappers for interactive use."""
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

    ET.SubElement(
        svg,
        "rect",
        {"x": "0", "y": "0", "width": f"{tw:.2f}", "height": f"{th:.2f}", "fill": _FILL_BACKGROUND},
    )

    defs = ET.SubElement(svg, "defs")

    def _entity_group(parent: ET.Element, eid: str, kind_str: str) -> ET.Element:
        ep, ek = entity_info.get(eid, ("", kind_str))
        if ep:
            return ET.SubElement(
                parent,
                "g",
                {"class": "archml-entity", "data-entity-path": ep, "data-entity-kind": ek, "style": "cursor:pointer"},
            )
        return parent

    # Root boundary
    if diagram.root.id != "all":
        root_bl = plan.boundaries.get(diagram.root.id)
        if root_bl is not None:
            grp = _entity_group(svg, diagram.root.id, diagram.root.kind)
            _render_boundary(grp, diagram.root.label, root_bl, scale, kind=diagram.root.kind)

    # Nested boundaries (BFS order, outermost first)
    nested: list[VizBoundary] = []
    _collect_nested_boundaries(diagram.root, nested)
    for bnd in nested:
        if bnd.id in plan.boundaries:
            grp = _entity_group(svg, bnd.id, bnd.kind)
            _render_boundary(grp, bnd.label, plan.boundaries[bnd.id], scale, kind=bnd.kind)

    # Node metadata
    node_meta: dict[str, tuple[str, str | None, NodeKind | None]] = {}
    _collect_node_meta(diagram.root, node_meta)
    for node in diagram.peripheral_nodes:
        node_meta[node.id] = (node.label, node.title, node.kind)

    # Nodes
    for node_id, nl in plan.nodes.items():
        label, title, kind = node_meta.get(node_id, (node_id, None, None))
        clip_id = _make_clip_id(node_id)
        _add_node_clip(defs, clip_id, nl, scale)
        grp = _entity_group(svg, node_id, kind or "")
        _render_node(grp, label, title, nl, kind, scale, clip_id)

    # Edges
    for edge in diagram.edges:
        route = plan.edge_routes.get(edge.id)
        if route is not None:
            _render_edge(svg, route.waypoints, edge.label, scale)

    return svg
