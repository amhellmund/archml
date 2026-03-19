# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""PNG diagram backend for ArchML architecture views.

Renders a :class:`~archml.views.topology.VizDiagram` using the pre-computed
:class:`~archml.views.placement.LayoutPlan` geometry, producing a PNG image
via the Pillow library.

The visual vocabulary and color palette match the SVG backend:

- Root boundary — slate-blue fill with a bold border and title label.
- Component — green tones.
- System — violet tones.
- User — amber tones.
- Channel — teal tones with a dashed border (communication conduit).
- External actors — slate-gray tones.
- Terminal nodes — yellow tones.
- Edges — dark navy polylines with filled arrowhead triangles.

Anti-aliasing is achieved via supersampling: the diagram is rendered at twice
the requested scale and then downsampled with a high-quality Lanczos filter.
This gives smooth edges without requiring a vector-capable rendering engine.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from archml.views.placement import BoundaryLayout, LayoutPlan, NodeLayout
from archml.views.topology import BoundaryKind, NodeKind, VizBoundary, VizDiagram, VizNode

# ###############
# Public Interface
# ###############


def render_png(
    diagram: VizDiagram,
    plan: LayoutPlan,
    output_path: Path,
    *,
    scale: float = 2.0,
) -> None:
    """Render *diagram* to a PNG file at *output_path*.

    The diagram is first rendered at 2× *scale* and then downsampled with
    Lanczos resampling for smooth anti-aliased edges.

    The output directory is created automatically if it does not exist.

    Args:
        diagram: The topology to render, as produced by
            :func:`~archml.views.topology.build_viz_diagram`.
        plan: The pre-computed layout plan produced by
            :func:`~archml.views.placement.compute_layout`.
        output_path: Destination path for the PNG file.
        scale: Base scale multiplier applied to all layout-unit coordinates.
            Defaults to ``2.0`` for a high-resolution export.
    """
    # Render at 2× scale for supersampling, then downsample.
    ss_scale = scale * 2.0
    img = _draw_diagram(diagram, plan, ss_scale)
    final_w = int(round(plan.total_width * scale))
    final_h = int(round(plan.total_height * scale))
    img = img.resize((final_w, final_h), Image.Resampling.LANCZOS)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")


# ################
# Implementation
# ################

# --- Color palette (RGB tuples, matches SVG backend) ---
_RGB_COMPONENT = (240, 253, 244)
_RGB_COMPONENT_STROKE = (22, 163, 74)
_RGB_SYSTEM = (245, 243, 255)
_RGB_SYSTEM_STROKE = (124, 58, 237)
_RGB_USER = (255, 251, 235)
_RGB_USER_STROKE = (217, 119, 6)
_RGB_CHANNEL = (240, 253, 250)
_RGB_CHANNEL_STROKE = (13, 148, 136)
_RGB_EXTERNAL = (248, 250, 252)
_RGB_EXTERNAL_STROKE = (71, 85, 105)
_RGB_TERMINAL = (254, 252, 232)
_RGB_TERMINAL_STROKE = (202, 138, 4)
_RGB_BOUNDARY = (239, 246, 255)
_RGB_BOUNDARY_STROKE = (37, 99, 235)
_RGB_EDGE = (30, 41, 59)
_RGB_TEXT = (30, 41, 59)
_RGB_BACKGROUND = (255, 255, 255)

_CORNER_RADIUS = 7
_BOUNDARY_STROKE_WIDTH = 3
_NODE_STROKE_WIDTH = 2
_EDGE_STROKE_WIDTH = 2
_ARROW_LEN = 10.0
_ARROW_HALF_W = 4.5
_BOUNDARY_LABEL_FONT_RATIO = 1.15  # boundary label is slightly larger than node labels
_EDGE_LABEL_FONT_RATIO = 0.85


def _node_colours(kind: NodeKind | None) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Return ``(fill_rgb, stroke_rgb)`` for a node kind."""
    if kind == "component":
        return _RGB_COMPONENT, _RGB_COMPONENT_STROKE
    if kind == "system":
        return _RGB_SYSTEM, _RGB_SYSTEM_STROKE
    if kind == "user":
        return _RGB_USER, _RGB_USER_STROKE
    if kind == "channel":
        return _RGB_CHANNEL, _RGB_CHANNEL_STROKE
    if kind in ("external_component", "external_system", "external_user"):
        return _RGB_EXTERNAL, _RGB_EXTERNAL_STROKE
    return _RGB_TERMINAL, _RGB_TERMINAL_STROKE


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a TrueType font at *size* points, falling back to the PIL default."""
    candidates: list[str] = []
    if sys.platform.startswith("linux"):
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/SFNSText.ttf",
        ]
    elif sys.platform == "win32":
        candidates = [
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]

    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue

    # Last resort: PIL's built-in bitmap font (Pillow 10.1+ supports size arg).
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float, float, float],
    radius: int,
    fill: tuple[int, int, int],
    outline: tuple[int, int, int],
    width: int,
    dashed: bool = False,
) -> None:
    """Draw a filled rounded rectangle with a solid or dashed outline."""
    x0, y0, x1, y1 = xy
    # Fill
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=fill, outline=None)
    # Outline
    if not dashed:
        draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=None, outline=outline, width=width)
    else:
        _draw_dashed_rounded_rect(draw, x0, y0, x1, y1, radius, outline, width)


def _draw_dashed_rounded_rect(
    draw: ImageDraw.ImageDraw,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    radius: int,
    colour: tuple[int, int, int],
    width: int,
) -> None:
    """Draw a dashed rounded-rectangle outline by sampling points along the perimeter."""
    # Build the perimeter as a sequence of (x, y) points.
    pts = _rounded_rect_perimeter(x0, y0, x1, y1, radius, steps_per_corner=12)
    # Draw dashes along the perimeter.
    dash_on = 10
    dash_off = 5
    total = len(pts)
    i = 0
    while i < total:
        end = min(i + dash_on, total)
        segment = pts[i:end]
        if len(segment) >= 2:
            for j in range(len(segment) - 1):
                draw.line([segment[j], segment[j + 1]], fill=colour, width=width)
        i += dash_on + dash_off


def _rounded_rect_perimeter(
    x0: float, y0: float, x1: float, y1: float, radius: int, steps_per_corner: int = 12
) -> list[tuple[float, float]]:
    """Return a list of (x, y) points tracing the rounded rectangle perimeter."""
    pts: list[tuple[float, float]] = []
    r = float(radius)
    # Top edge (left to right)
    pts += [(x0 + r, y0), (x1 - r, y0)]
    # Top-right corner
    cx, cy = x1 - r, y0 + r
    pts += _arc_pts(cx, cy, r, -math.pi / 2, 0, steps_per_corner)
    # Right edge (top to bottom)
    pts += [(x1, y0 + r), (x1, y1 - r)]
    # Bottom-right corner
    cx, cy = x1 - r, y1 - r
    pts += _arc_pts(cx, cy, r, 0, math.pi / 2, steps_per_corner)
    # Bottom edge (right to left)
    pts += [(x1 - r, y1), (x0 + r, y1)]
    # Bottom-left corner
    cx, cy = x0 + r, y1 - r
    pts += _arc_pts(cx, cy, r, math.pi / 2, math.pi, steps_per_corner)
    # Left edge (bottom to top)
    pts += [(x0, y1 - r), (x0, y0 + r)]
    # Top-left corner
    cx, cy = x0 + r, y0 + r
    pts += _arc_pts(cx, cy, r, math.pi, 3 * math.pi / 2, steps_per_corner)
    return pts


def _arc_pts(cx: float, cy: float, r: float, start: float, end: float, steps: int) -> list[tuple[float, float]]:
    """Return points along a circular arc from *start* to *end* radians."""
    return [
        (cx + r * math.cos(start + (end - start) * i / steps), cy + r * math.sin(start + (end - start) * i / steps))
        for i in range(steps + 1)
    ]


def _draw_diagram(diagram: VizDiagram, plan: LayoutPlan, scale: float) -> Image.Image:
    """Render the full diagram at *scale* into a Pillow ``Image``."""
    w = max(1, int(math.ceil(plan.total_width * scale)))
    h = max(1, int(math.ceil(plan.total_height * scale)))
    img = Image.new("RGB", (w, h), _RGB_BACKGROUND)
    draw = ImageDraw.Draw(img)

    font_size = max(8, int(11 * scale))
    font = _load_font(font_size)
    bold_font = _load_font(max(9, int(12 * scale)))

    # Build node metadata map (direct VizNode children + inner nodes of VizBoundary children)
    node_meta: dict[str, tuple[str, str | None, NodeKind | None]] = {}
    for child in diagram.root.children:
        if isinstance(child, VizNode):
            node_meta[child.id] = (child.label, child.title, child.kind)
        elif isinstance(child, VizBoundary):
            for inner in child.children:
                if isinstance(inner, VizNode):
                    node_meta[inner.id] = (inner.label, inner.title, inner.kind)
    for node in diagram.peripheral_nodes:
        node_meta[node.id] = (node.label, node.title, node.kind)

    small_font = _load_font(max(7, int(9 * scale)))

    # Draw root boundary
    if diagram.root.id in plan.boundaries:
        bl = plan.boundaries[diagram.root.id]
        _draw_boundary(draw, diagram.root.label, bl, scale, bold_font)

    # Draw nested boundaries (expanded sub-systems/components) behind their nodes
    for child in diagram.root.children:
        if isinstance(child, VizBoundary) and child.id in plan.boundaries:
            _draw_boundary(draw, child.label, plan.boundaries[child.id], scale, bold_font, kind=child.kind)

    # Draw all positioned nodes
    for node_id, nl in plan.nodes.items():
        label, title, kind = node_meta.get(node_id, (node_id, None, None))
        _draw_node(draw, label, title, nl, kind, scale, font, small_font)

    # Draw edges
    edge_font = _load_font(max(7, int(10 * scale * _EDGE_LABEL_FONT_RATIO)))
    for edge in diagram.edges:
        route = plan.edge_routes.get(edge.id)
        if route is not None:
            _draw_edge(draw, route.waypoints, edge.label, scale, edge_font)

    return img


def _draw_boundary(
    draw: ImageDraw.ImageDraw,
    label: str,
    bl: BoundaryLayout,
    scale: float,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    *,
    kind: BoundaryKind | None = None,
) -> None:
    """Draw a boundary rectangle with a fill, border, and title label.

    *kind* selects the colour palette: ``"component"`` uses green tones,
    ``"system"`` uses violet tones.  ``None`` (the default, used for the root
    boundary) uses the slate-blue palette.
    """
    if kind == "component":
        fill, stroke = _RGB_COMPONENT, _RGB_COMPONENT_STROKE
    elif kind == "system":
        fill, stroke = _RGB_SYSTEM, _RGB_SYSTEM_STROKE
    else:
        fill, stroke = _RGB_BOUNDARY, _RGB_BOUNDARY_STROKE
    x0 = bl.x * scale
    y0 = bl.y * scale
    x1 = (bl.x + bl.width) * scale
    y1 = (bl.y + bl.height) * scale
    _draw_rounded_rect(draw, (x0, y0, x1, y1), _CORNER_RADIUS, fill, stroke, _BOUNDARY_STROKE_WIDTH)
    # Title label: 15 layout units below the boundary top edge (matches SVG _BOUNDARY_LABEL_OFFSET)
    tx = (x0 + x1) / 2
    ty = y0 + 15 * scale
    draw.text((tx, ty), label, fill=stroke, font=font, anchor="mm")


def _draw_node(
    draw: ImageDraw.ImageDraw,
    label: str,
    title: str | None,
    nl: NodeLayout,
    kind: NodeKind | None,
    scale: float,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    small_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    """Draw a node rectangle with a centred label.

    For channel nodes, renders two lines: the interface name (larger, *title*
    or *label*) above centre and the channel name (smaller, ``$label``) below.
    """
    fill, stroke = _node_colours(kind)
    x0 = nl.x * scale
    y0 = nl.y * scale
    x1 = (nl.x + nl.width) * scale
    y1 = (nl.y + nl.height) * scale
    dashed = kind == "channel"
    _draw_rounded_rect(draw, (x0, y0, x1, y1), _CORNER_RADIUS, fill, stroke, _NODE_STROKE_WIDTH, dashed=dashed)
    tx = (x0 + x1) / 2
    ty = (y0 + y1) / 2
    if kind == "channel":
        iface_name = title if title is not None else label
        line_gap = 6 * scale
        draw.text((tx, ty - line_gap * 0.5), iface_name, fill=_RGB_TEXT, font=font, anchor="mm")
        draw.text((tx, ty + line_gap * 0.9), f"${label}", fill=_RGB_TEXT, font=small_font, anchor="mm")
    else:
        draw.text((tx, ty), label, fill=_RGB_TEXT, font=font, anchor="mm")


def _draw_edge(
    draw: ImageDraw.ImageDraw,
    waypoints: list[tuple[float, float]],
    label: str,
    scale: float,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    """Draw an edge polyline with a filled arrowhead and a midpoint label."""
    if len(waypoints) < 2:
        return

    scaled = [(x * scale, y * scale) for x, y in waypoints]

    x1, y1 = scaled[-2]
    x2, y2 = scaled[-1]
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return

    ndx, ndy = dx / length, dy / length
    arrow_len = min(_ARROW_LEN * scale, length * 0.45)
    base_x = x2 - arrow_len * ndx
    base_y = y2 - arrow_len * ndy

    # Edge body
    body = list(scaled[:-1]) + [(base_x, base_y)]
    for i in range(len(body) - 1):
        draw.line([body[i], body[i + 1]], fill=_RGB_EDGE, width=_EDGE_STROKE_WIDTH)

    # Arrowhead
    hw = _ARROW_HALF_W * scale
    lx = base_x - hw * ndy
    ly = base_y + hw * ndx
    rx = base_x + hw * ndy
    ry = base_y - hw * ndx
    draw.polygon([(x2, y2), (lx, ly), (rx, ry)], fill=_RGB_EDGE)
