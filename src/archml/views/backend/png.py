# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""PNG diagram backend for ArchML architecture views.

Renders a :class:`~archml.views.topology.VizDiagram` using the pre-computed
:class:`~archml.views.placement.LayoutPlan` geometry, producing a PNG image
via the Pillow library.

The visual vocabulary and color palette match the SVG backend:

- Root boundary — no box drawn (top-level architecture is not framed).
- Component — orange tones.
- System — blue tones.
- User — amber tones.
- Channel / interface — red tones with a dashed border.
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
# Components (orange family)
_RGB_COMPONENT = (255, 247, 237)
_RGB_COMPONENT_STROKE = (234, 88, 12)
# Systems (blue family)
_RGB_SYSTEM = (239, 246, 255)
_RGB_SYSTEM_STROKE = (37, 99, 235)
_RGB_USER = (255, 251, 235)
_RGB_USER_STROKE = (217, 119, 6)
# Channels / interfaces (red family, dashed border)
_RGB_CHANNEL = (254, 242, 242)
_RGB_CHANNEL_STROKE = (220, 38, 38)
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

# Channel / interface node layout — must match LayoutConfig defaults.
_CHANNEL_LINE_GAP = 8.0  # explicit gap (layout units) between the two text lines
_CHANNEL_LABEL_FONT_RATIO = 0.9  # channel-label font size relative to interface-name font size


def _node_colours(kind: NodeKind | None) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Return ``(fill_rgb, stroke_rgb)`` for a node kind."""
    if kind == "component":
        return _RGB_COMPONENT, _RGB_COMPONENT_STROKE
    if kind == "system":
        return _RGB_SYSTEM, _RGB_SYSTEM_STROKE
    if kind == "user":
        return _RGB_USER, _RGB_USER_STROKE
    if kind in ("channel", "interface"):
        return _RGB_CHANNEL, _RGB_CHANNEL_STROKE
    if kind in ("external_component", "external_system", "external_user"):
        return _RGB_EXTERNAL, _RGB_EXTERNAL_STROKE
    return _RGB_TERMINAL, _RGB_TERMINAL_STROKE


def _load_font(
    size: int,
    *,
    bold: bool = False,
    italic: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a TrueType font at *size* points, falling back to the PIL default.

    Args:
        size: Font size in points.
        bold: Request a bold typeface variant.
        italic: Request an italic/oblique typeface variant.
    """
    candidates: list[str] = []
    if sys.platform.startswith("linux"):
        if bold and italic:
            candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBoldOblique.ttf",
                "/usr/share/fonts/truetype/ubuntu/Ubuntu-BI.ttf",
            ]
        elif bold:
            candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
                "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
            ]
        elif italic:
            candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansOblique.ttf",
                "/usr/share/fonts/truetype/ubuntu/Ubuntu-RI.ttf",
            ]
        else:
            candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
                "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
            ]
    elif sys.platform == "darwin":
        if bold and italic:
            candidates = ["/Library/Fonts/Arial Bold Italic.ttf", "/Library/Fonts/Helvetica Bold Oblique.ttf"]
        elif bold:
            candidates = ["/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"]
        elif italic:
            candidates = ["/Library/Fonts/Arial Italic.ttf", "/Library/Fonts/Helvetica Oblique.ttf"]
        else:
            candidates = [
                "/System/Library/Fonts/Helvetica.ttc",
                "/Library/Fonts/Arial.ttf",
                "/System/Library/Fonts/SFNSText.ttf",
            ]
    elif sys.platform == "win32":
        if bold and italic:
            candidates = ["C:/Windows/Fonts/arialbi.ttf", "C:/Windows/Fonts/segoeuiz.ttf"]
        elif bold:
            candidates = ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf"]
        elif italic:
            candidates = ["C:/Windows/Fonts/ariali.ttf", "C:/Windows/Fonts/segoeuii.ttf"]
        else:
            candidates = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"]

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
    """Draw a dashed rounded-rectangle outline by sampling points along the perimeter.

    Straight edges are sampled at 2 px intervals so the point-count-based
    dash algorithm produces uniform dashes on every side (not just on arcs).
    ``dash_on=6`` and ``dash_off=3`` points yield roughly 12 px on / 6 px off
    in the supersampled image, which halves to ~6 px on / 3 px off in the
    final output — visually close to SVG's ``stroke-dasharray="5,3"``.
    """
    pts = _rounded_rect_perimeter(x0, y0, x1, y1, radius, steps_per_corner=12, sample_step=2.0)
    dash_on = 6
    dash_off = 3
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
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    radius: int,
    steps_per_corner: int = 12,
    sample_step: float = 0.0,
) -> list[tuple[float, float]]:
    """Return a list of (x, y) points tracing the rounded rectangle perimeter.

    When *sample_step* > 0, straight edges are densely sampled at that pixel
    interval so that point-count-based dashing produces uniform dash lengths
    on every side.  When *sample_step* is 0 (default), each straight edge is
    represented by its two endpoints only (suitable for solid outlines).
    """
    r = float(radius)

    def _seg(ax: float, ay: float, bx: float, by: float) -> list[tuple[float, float]]:
        if sample_step <= 0:
            return [(ax, ay), (bx, by)]
        length = math.hypot(bx - ax, by - ay)
        n = max(2, int(length / sample_step) + 1)
        return [(ax + (bx - ax) * i / (n - 1), ay + (by - ay) * i / (n - 1)) for i in range(n)]

    pts: list[tuple[float, float]] = []
    # Top edge (left to right)
    pts += _seg(x0 + r, y0, x1 - r, y0)
    # Top-right corner
    pts += _arc_pts(x1 - r, y0 + r, r, -math.pi / 2, 0, steps_per_corner)
    # Right edge (top to bottom)
    pts += _seg(x1, y0 + r, x1, y1 - r)
    # Bottom-right corner
    pts += _arc_pts(x1 - r, y1 - r, r, 0, math.pi / 2, steps_per_corner)
    # Bottom edge (right to left)
    pts += _seg(x1 - r, y1, x0 + r, y1)
    # Bottom-left corner
    pts += _arc_pts(x0 + r, y1 - r, r, math.pi / 2, math.pi, steps_per_corner)
    # Left edge (bottom to top)
    pts += _seg(x0, y1 - r, x0, y0 + r)
    # Top-left corner
    pts += _arc_pts(x0 + r, y0 + r, r, math.pi, 3 * math.pi / 2, steps_per_corner)
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

    font_size = max(10, int(15 * scale))
    font = _load_font(font_size)
    bold_font = _load_font(max(11, int(16 * scale)), bold=True)
    node_bold_font = _load_font(font_size, bold=True)
    channel_label_font_size = max(7, int(font_size * _CHANNEL_LABEL_FONT_RATIO))
    channel_label_font = _load_font(channel_label_font_size, italic=True)

    # Build node metadata map recursively from all leaf VizNodes
    node_meta: dict[str, tuple[str, str | None, NodeKind | None]] = {}
    _collect_node_meta(diagram.root, node_meta)
    for node in diagram.peripheral_nodes:
        node_meta[node.id] = (node.label, node.title, node.kind)

    # Root boundary — draw a box for real entities; skip only the synthetic
    # "all" diagram whose root has id "all".
    if diagram.root.id != "all":
        root_bl = plan.boundaries.get(diagram.root.id)
        if root_bl is not None:
            _draw_boundary(draw, diagram.root.label, root_bl, scale, bold_font, kind=diagram.root.kind)

    # Draw nested boundaries outermost-first so inner ones appear on top
    nested: list[VizBoundary] = []
    _collect_nested_boundaries(diagram.root, nested)
    for bnd in nested:
        if bnd.id in plan.boundaries:
            _draw_boundary(draw, bnd.label, plan.boundaries[bnd.id], scale, bold_font, kind=bnd.kind)

    # Draw all positioned nodes
    for node_id, nl in plan.nodes.items():
        label, title, kind = node_meta.get(node_id, (node_id, None, None))
        _draw_node(draw, label, title, nl, kind, scale, font, node_bold_font, channel_label_font)

    # Draw edges
    edge_font = _load_font(max(7, int(10 * scale * _EDGE_LABEL_FONT_RATIO)))
    for edge in diagram.edges:
        route = plan.edge_routes.get(edge.id)
        if route is not None:
            _draw_edge(draw, route.waypoints, edge.label, scale, edge_font)

    return img


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

    *kind* selects the colour palette: ``"component"`` uses orange tones,
    ``"system"`` uses blue tones.  ``None`` (the default) falls back to the
    blue boundary palette.
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
    # Title label: 18 layout units below the boundary top edge (matches SVG _BOUNDARY_LABEL_OFFSET)
    tx = (x0 + x1) / 2
    ty = y0 + 21 * scale
    draw.text((tx, ty), label, fill=stroke, font=font, anchor="mm")


def _draw_node(
    draw: ImageDraw.ImageDraw,
    label: str,
    title: str | None,
    nl: NodeLayout,
    kind: NodeKind | None,
    scale: float,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    bold_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    channel_label_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    """Draw a node rectangle with a centred label.

    For channel nodes, renders two lines: the bold interface name above and
    the smaller italic channel label below, separated by ``_CHANNEL_LINE_GAP``.
    For ``component`` and ``system`` nodes the label is drawn in bold.
    """
    fill, stroke = _node_colours(kind)
    x0 = nl.x * scale
    y0 = nl.y * scale
    x1 = (nl.x + nl.width) * scale
    y1 = (nl.y + nl.height) * scale
    dashed = kind in ("channel", "interface")
    _draw_rounded_rect(draw, (x0, y0, x1, y1), _CORNER_RADIUS, fill, stroke, _NODE_STROKE_WIDTH, dashed=dashed)
    tx = (x0 + x1) / 2
    # cy_mid in layout units; compute pixel positions using the same formula as SVG.
    cy_mid = nl.y + nl.height / 2
    if kind == "channel":
        iface_name = title if title is not None else label
        # Mirror the SVG two-line block-centering formula (all values in layout units).
        fs = 15.0
        fs_small = fs * _CHANNEL_LABEL_FONT_RATIO
        gap = _CHANNEL_LINE_GAP
        line1_y = (cy_mid - (fs_small + gap) / 2) * scale
        line2_y = (cy_mid + (fs + gap) / 2) * scale
        draw.text((tx, line1_y), iface_name, fill=_RGB_TEXT, font=bold_font, anchor="mm")
        draw.text((tx, line2_y), f"${label}", fill=_RGB_TEXT, font=channel_label_font, anchor="mm")
    elif kind in ("component", "system", "interface"):
        draw.text((tx, cy_mid * scale), label, fill=_RGB_TEXT, font=bold_font, anchor="mm")
    else:
        draw.text((tx, cy_mid * scale), label, fill=_RGB_TEXT, font=font, anchor="mm")


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
