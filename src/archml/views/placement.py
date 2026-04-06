# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Layout data types and shared helpers for ArchML visualization diagrams.

This module defines the backend-independent :class:`LayoutPlan` and its
component types (:class:`LayoutConfig`, :class:`NodeLayout`,
:class:`BoundaryLayout`, :class:`PortAnchor`, :class:`EdgeRoute`), plus
sizing and routing helpers used by the Graphviz layout backend.

The actual layout computation is done by
:func:`~archml.views.layout.compute_layout`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from archml.views.topology import VizBoundary, VizNode, VizPort

# ###############
# Public Interface
# ###############


@dataclass
class LayoutConfig:
    """Configuration parameters for the placement algorithm.

    All dimensions are in abstract layout units.  Renderers scale them to
    actual pixel or viewport sizes.

    Attributes:
        node_width: Minimum width of every internal child node.  The effective
            width is ``max(node_width, label_text_width + text_h_padding)``
            computed uniformly across all inner nodes so that the longest label
            always fits.
        node_height: Minimum height of every internal child node.  For channel
            nodes the effective height is also bounded below by
            ``_min_channel_node_height(config)`` so that both text lines and the
            explicit gap fit comfortably.
        layer_gap: Horizontal gap between adjacent node columns inside the
            root boundary.
        node_gap: Vertical gap between nodes stacked in the same column.
        peripheral_gap: Horizontal gap between peripheral nodes and the root
            boundary edge.
        boundary_padding: Padding between a boundary edge and its nearest
            child node on each side.
        boundary_title_reserve: Vertical space reserved at the top of every
            boundary box for the title label.
        boundary_bottom_extra_padding: Additional vertical padding at the
            bottom of a boundary box (used by some renderers).
        peripheral_node_width: Minimum width of terminal and external peripheral
            nodes.  Expanded the same way as ``node_width``.
        peripheral_node_height: Height of terminal and external peripheral nodes.
        approx_char_width: Estimated width of one character in layout units at
            the default rendering scale (11 pt font at scale 1 ≈ 6.6 lu/char;
            the default 7.0 adds a small safety margin).  Used to compute
            minimum node widths that accommodate label text.
        bold_char_width_factor: Multiplier applied to ``approx_char_width`` when
            estimating the width of bold text.  Bold glyphs are typically ~10 %
            wider than their regular counterparts.
        text_h_padding: Total horizontal padding (both sides) added on top of
            the text-width estimate when sizing node boxes.
        font_size: Base font size in layout units (≈ px at scale 1.0).  Used to
            compute the minimum height of nodes that contain multi-line text.
        node_v_padding: Total vertical padding (top + bottom) inside a node box.
            Ensures text never touches the top or bottom border.
        channel_line_gap: Explicit gap in layout units inserted between the
            interface name line and the channel-name line inside channel nodes.
            Must match the ``_CHANNEL_LINE_GAP`` constant used by each renderer.
        channel_label_font_ratio: Font-size ratio of the channel label relative
            to the interface name.  Must match the renderer constant
            ``_CHANNEL_LABEL_FONT_RATIO``.
        boundary_title_font_ratio: Font-size ratio of the boundary title relative to
            the base ``font_size``.  Must match the renderer constant
            ``_FONT_SIZE * scale * 1.1`` used by ``_render_boundary`` in the SVG
            backend.  Used to compute the minimum content width needed so that
            boundary titles always fit within their bounding box.
        user_icon_size: Side length of the SVG symbol icon rendered in the top-left
            corner of user and external_user nodes (layout units).  Must match the
            ``_USER_ICON_SIZE`` constant in the diagram renderer.
        user_icon_pad: Padding from the node top and left edges to the icon
            (layout units).  Controls the minimum height required by user nodes.
            Must match ``_USER_ICON_PAD`` in the diagram renderer.
        diagram_margin: Uniform whitespace added around the entire diagram on
            all four sides (layout units).  Prevents box strokes from being
            clipped at the SVG/PNG canvas edge when there are no peripheral
            nodes on a given side.
        edge_margin: Visual clearance in layout units kept between a routed edge
            and every component/boundary box the edge does *not* need to enter.
            The very first segment (exiting the source port) and the very last
            segment (entering the target port) are exempt so that connections
            can reach their nodes.  All other routing decisions — corridor
            selection and bypass levels — treat non-source/non-target boxes as
            inflated by this amount on every side.
        y_optimisation_passes: Number of iterative barycenter passes used to
            optimise the vertical positions of nodes within each layer.  Each
            pass moves every node toward the average y-centre of its connected
            neighbours and then re-enforces non-overlap constraints.  More
            passes give tighter alignment at the cost of slightly more
            computation.  Set to ``0`` to fall back to the plain uniform-
            spacing assignment.
    """

    node_width: float = 120.0
    node_height: float = 80.0
    layer_gap: float = 80.0
    node_gap: float = 40.0
    peripheral_gap: float = 80.0
    boundary_padding: float = 40.0
    boundary_title_reserve: float = 35.0
    boundary_bottom_extra_padding: float = 15.0
    peripheral_node_width: float = 100.0
    peripheral_node_height: float = 68.0
    approx_char_width: float = 9.5
    bold_char_width_factor: float = 1.1
    text_h_padding: float = 24.0
    font_size: float = 15.0
    node_v_padding: float = 28.0
    channel_line_gap: float = 8.0
    channel_label_font_ratio: float = 0.9
    boundary_title_font_ratio: float = 1.1
    user_icon_size: float = 20.0
    user_icon_pad: float = 8.0
    diagram_margin: float = 4.0
    edge_margin: float = 8.0
    y_optimisation_passes: int = 6


@dataclass
class PortAnchor:
    """The exact point where an edge attaches to a port.

    Attributes:
        port_id: Stable identifier of the :class:`~archml.views.topology.VizPort`.
        x: Horizontal position of the attachment point (layout units).
        y: Vertical position of the attachment point (layout units).
    """

    port_id: str
    x: float
    y: float


@dataclass
class NodeLayout:
    """Position and size of a :class:`~archml.views.topology.VizNode`.

    The origin ``(x, y)`` is the **top-left corner** of the node rectangle.
    The node spans ``[x, x + width] × [y, y + height]``.

    Attributes:
        node_id: Stable identifier matching :attr:`VizNode.id`.
        x: Left edge (layout units).
        y: Top edge (layout units).
        width: Horizontal extent (layout units).
        height: Vertical extent (layout units).
    """

    node_id: str
    x: float
    y: float
    width: float
    height: float


@dataclass
class BoundaryLayout:
    """Position and size of a :class:`~archml.views.topology.VizBoundary`.

    Attributes:
        boundary_id: Stable identifier matching :attr:`VizBoundary.id`.
        x: Left edge (layout units).
        y: Top edge (layout units).
        width: Horizontal extent (layout units).
        height: Vertical extent (layout units).
    """

    boundary_id: str
    x: float
    y: float
    width: float
    height: float


@dataclass
class EdgeRoute:
    """Polyline route for a :class:`~archml.views.topology.VizEdge`.

    The route is expressed as an ordered list of ``(x, y)`` waypoints.  The
    first waypoint coincides with the source port anchor; the last with the
    target port anchor.  Interior waypoints create the orthogonal bends: for
    a Z-shaped route there are two interior waypoints, one at the end of the
    horizontal segment out of the source and one at the start of the
    horizontal segment into the target.

    Attributes:
        edge_id: Stable identifier matching :attr:`VizEdge.id`.
        waypoints: Ordered ``(x, y)`` coordinate pairs (layout units).
    """

    edge_id: str
    waypoints: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class LayoutPlan:
    """Complete backend-independent layout plan for a :class:`~archml.views.topology.VizDiagram`.

    All positions and sizes are in abstract layout units.

    Attributes:
        diagram_id: Matches :attr:`VizDiagram.id`.
        total_width: Bounding-box width of the entire diagram (layout units).
        total_height: Bounding-box height of the entire diagram (layout units).
        nodes: Mapping from node ID to its :class:`NodeLayout`.  Covers all
            internal child nodes and all peripheral nodes.
        boundaries: Mapping from boundary ID to its :class:`BoundaryLayout`.
            Covers the root boundary and all nested boundaries.
        port_anchors: Mapping from port ID to its :class:`PortAnchor`.
            Covers ports on every node and boundary in the diagram.
        edge_routes: Mapping from edge ID to its :class:`EdgeRoute`.  Only
            edges whose both port anchors are resolved are included.
    """

    diagram_id: str
    total_width: float
    total_height: float
    nodes: dict[str, NodeLayout] = field(default_factory=dict)
    boundaries: dict[str, BoundaryLayout] = field(default_factory=dict)
    port_anchors: dict[str, PortAnchor] = field(default_factory=dict)
    edge_routes: dict[str, EdgeRoute] = field(default_factory=dict)


# -------- text-aware sizing helpers --------


def _required_text_width(text: str, cfg: LayoutConfig, *, bold: bool = False, font_ratio: float = 1.0) -> float:
    """Estimated minimum box width needed to display *text* without clipping.

    Args:
        text: The string to be rendered.
        cfg: Layout configuration supplying character-width estimates.
        bold: When ``True``, ``cfg.bold_char_width_factor`` is applied to
            account for the wider glyphs of bold typefaces.
        font_ratio: Additional scale factor applied to the character-width
            estimate.  Use ``cfg.channel_label_font_ratio`` when sizing for
            the smaller channel-label line so the estimate matches the actual
            rendered font size.
    """
    char_w = cfg.approx_char_width * (cfg.bold_char_width_factor if bold else 1.0) * font_ratio
    return len(text) * char_w + cfg.text_h_padding


def _min_channel_node_height(cfg: LayoutConfig) -> float:
    """Minimum node height needed to fit two lines of text with an explicit gap."""
    line1_h = cfg.font_size
    line2_h = cfg.font_size * cfg.channel_label_font_ratio
    return line1_h + cfg.channel_line_gap + line2_h + cfg.node_v_padding


def _effective_inner_size(nodes: list[VizNode], cfg: LayoutConfig) -> tuple[float, float]:
    """Return ``(width, height)`` for inner child nodes.

    Width is ``max(cfg.node_width, max_required_text_width)`` computed
    uniformly so every label fits.  Height accounts for channel nodes.
    """
    w = cfg.node_width
    h = cfg.node_height
    for node in nodes:
        if node.kind == "channel":
            iface = node.title if node.title else node.label
            needed = max(
                _required_text_width(iface, cfg, bold=True),
                _required_text_width(f"${node.label}", cfg, font_ratio=cfg.channel_label_font_ratio),
            )
            h = max(h, _min_channel_node_height(cfg))
        elif node.kind in ("component", "system"):
            needed = _required_text_width(node.label, cfg, bold=True)
        elif node.kind in ("user", "external_user"):
            needed = _required_text_width(node.label, cfg)
            # Icon badge in top-left corner: must fit vertically alongside the centred label.
            icon_min_h = (
                cfg.user_icon_pad + cfg.user_icon_size + cfg.user_icon_pad + cfg.font_size + cfg.node_v_padding / 2
            )
            h = max(h, icon_min_h)
        else:
            needed = _required_text_width(node.label, cfg)
        w = max(w, needed)
    return w, h


def _effective_peripheral_size(nodes: list[VizNode], cfg: LayoutConfig) -> tuple[float, float]:
    """Return ``(width, height)`` for peripheral nodes."""
    w = cfg.peripheral_node_width
    h = cfg.peripheral_node_height
    for node in nodes:
        needed = _required_text_width(node.label, cfg)
        w = max(w, needed)
        if node.kind in ("user", "external_user"):
            icon_min_h = (
                cfg.user_icon_pad + cfg.user_icon_size + cfg.user_icon_pad + cfg.font_size + cfg.node_v_padding / 2
            )
            h = max(h, icon_min_h)
    return w, h


# -------- coordinate helpers --------


def _stack_height(count: int, item_h: float, gap: float) -> float:
    """Total height of *count* uniformly-sized items stacked with *gap* between them."""
    if count <= 0:
        return 0.0
    return count * item_h + max(0, count - 1) * gap


def _stack_height_variable(heights: list[float], gap: float) -> float:
    """Total height of variably-sized items stacked with *gap* between them."""
    if not heights:
        return 0.0
    return sum(heights) + max(0, len(heights) - 1) * gap


def _add_node_anchors(
    node: VizNode,
    layout: NodeLayout,
    out: dict[str, PortAnchor],
) -> None:
    """Compute and record port anchors for a :class:`VizNode`.

    ``requires`` ports are anchored to the **left edge** (x = layout.x).
    ``provides`` ports are anchored to the **right edge** (x = layout.x + width).
    Multiple ports on the same side are spaced evenly along the vertical axis.
    """
    req = [p for p in node.ports if p.direction == "requires"]
    prov = [p for p in node.ports if p.direction == "provides"]
    _anchor_ports_on_edge(req, layout.x, layout.y, layout.height, out)
    _anchor_ports_on_edge(prov, layout.x + layout.width, layout.y, layout.height, out)


def _add_boundary_anchors(
    boundary: VizBoundary,
    layout: BoundaryLayout,
    out: dict[str, PortAnchor],
) -> None:
    """Compute and record port anchors for a :class:`VizBoundary`.

    Follows the same left/right convention as :func:`_add_node_anchors`.
    """
    req = [p for p in boundary.ports if p.direction == "requires"]
    prov = [p for p in boundary.ports if p.direction == "provides"]
    _anchor_ports_on_edge(req, layout.x, layout.y, layout.height, out)
    _anchor_ports_on_edge(prov, layout.x + layout.width, layout.y, layout.height, out)


def _anchor_ports_on_edge(
    ports: list[VizPort],
    edge_x: float,
    top_y: float,
    height: float,
    out: dict[str, PortAnchor],
) -> None:
    """Place *ports* evenly along a vertical edge at x = *edge_x*."""
    n = len(ports)
    if n == 0:
        return
    for i, port in enumerate(ports):
        y = top_y + (i + 1) * height / (n + 1)
        out[port.id] = PortAnchor(port_id=port.id, x=edge_x, y=y)


# -------- obstacle-aware orthogonal routing --------

# An obstacle is a bounding rectangle (x, y, width, height).
_Rect = tuple[float, float, float, float]


def _segment_h_clear(y: float, x1: float, x2: float, obstacles: list[_Rect]) -> bool:
    """Return ``True`` if the horizontal segment at *y* from *x1* to *x2* is obstacle-free.

    A segment is considered blocked when it *strictly* enters an obstacle
    rectangle.  Port anchors sit on the outer edge of their node (not strictly
    inside), so they are never counted as blocked by their own node.
    """
    lo, hi = (x1, x2) if x1 <= x2 else (x2, x1)
    return all(not (ox < hi and ox + ow > lo and oy < y < oy + oh) for ox, oy, ow, oh in obstacles)


def _segment_v_clear(x: float, y1: float, y2: float, obstacles: list[_Rect]) -> bool:
    """Return ``True`` if the vertical segment at *x* from *y1* to *y2* is obstacle-free."""
    lo, hi = (y1, y2) if y1 <= y2 else (y2, y1)
    return all(not (oy < hi and oy + oh > lo and ox < x < ox + ow) for ox, oy, ow, oh in obstacles)


def _route_is_clear(waypoints: list[tuple[float, float]], obstacles: list[_Rect]) -> bool:
    """Return ``True`` if every segment of the polyline *waypoints* avoids all obstacles."""
    for i in range(len(waypoints) - 1):
        x1, y1 = waypoints[i]
        x2, y2 = waypoints[i + 1]
        if abs(x1 - x2) < 0.5:  # vertical
            if not _segment_v_clear(x1, y1, y2, obstacles):
                return False
        else:  # horizontal
            if not _segment_h_clear(y1, x1, x2, obstacles):
                return False
    return True


def _free_corridor_xs(sx: float, tx: float, obstacles: list[_Rect]) -> list[float]:
    """Return sorted x-midpoints of free vertical corridors in the open interval (sx, tx).

    A *corridor* is a contiguous x-range within ``(sx, tx)`` not covered by
    any obstacle's x-extent.  Routing vertical segments through a corridor
    midpoint guarantees the segment avoids all obstacles.

    Args:
        sx: Left boundary of the search range (source port x).
        tx: Right boundary of the search range (target port x).
        obstacles: Axis-aligned obstacle rectangles.

    Returns:
        Sorted list of x midpoints, one per free corridor.  Empty when
        ``tx <= sx`` or no free corridor exists.
    """
    if tx <= sx:
        return []
    # Clip obstacle x-extents to the open interval (sx, tx).
    blocked: list[tuple[float, float]] = []
    for ox, _oy, ow, _oh in obstacles:
        lo = max(ox, sx)
        hi = min(ox + ow, tx)
        if lo < hi:
            blocked.append((lo, hi))
    blocked.sort()
    # Merge overlapping ranges.
    merged: list[list[float]] = []
    for lo, hi in blocked:
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    # Corridors are the gaps between (and outside) the merged blocked ranges.
    corridors: list[float] = []
    prev = sx
    for lo, hi in merged:
        if lo > prev + 0.5:
            corridors.append((prev + lo) / 2.0)
        prev = hi
    if tx > prev + 0.5:
        corridors.append((prev + tx) / 2.0)
    return corridors


def _bypass_levels(
    x1: float,
    x2: float,
    obstacles: list[_Rect],
    total_height: float,
    gap: float,
) -> list[float]:
    """Return candidate y-levels for a horizontal bypass between *x1* and *x2*.

    The bypass levels are placed just *above* and just *below* all obstacles
    whose x-extents overlap ``[x1, x2]``.  The above level is returned first
    so that shorter upward detours are preferred.

    Args:
        x1: Left edge of the x-range to check.
        x2: Right edge of the x-range to check.
        obstacles: Axis-aligned obstacle rectangles.
        total_height: Canvas height — used as the lower bound for the
            below-all-content bypass level.
        gap: Clearance to add above/below the obstacle bounding box.

    Returns:
        Up to two candidate y values.  Empty list when no obstacles overlap
        the given x-range (no bypass needed).
    """
    lo_x, hi_x = min(x1, x2), max(x1, x2)
    relevant = [obs for obs in obstacles if obs[0] < hi_x and obs[0] + obs[2] > lo_x]
    if not relevant:
        return []
    top = min(obs[1] for obs in relevant)
    bottom = max(obs[1] + obs[3] for obs in relevant)
    return [top - gap, bottom + gap]


def _inflate_obstacles(
    obstacles: list[_Rect],
    sx: float,
    tx: float,
    margin: float,
) -> list[_Rect]:
    """Return obstacles with non-source/non-target boxes expanded by *margin* on every side.

    The **source node** (identified by right edge ≈ *sx*) and the **target
    node** (identified by left edge ≈ *tx*) are returned at their original
    size so that connection segments can reach their port anchors without the
    margin zone preventing the entry/exit.  All other obstacle boxes are
    inflated by *margin*, which makes corridor and clearance checks
    automatically maintain that clearance from every side of those boxes.

    When *margin* is zero or negative the original list is returned unchanged.

    Args:
        obstacles: Original obstacle rectangles ``(x, y, width, height)``.
        sx: x-coordinate of the source port anchor (= right edge of source node).
        tx: x-coordinate of the target port anchor (= left edge of target node).
        margin: Inflation amount (layout units) added to each side of
            non-source/non-target obstacles.

    Returns:
        A new list of obstacle rectangles.
    """
    if margin <= 0.0:
        return list(obstacles)
    result: list[_Rect] = []
    for ox, oy, ow, oh in obstacles:
        if abs(ox + ow - sx) < 0.5 or abs(ox - tx) < 0.5:
            # Source node (right edge = sx) or target node (left edge = tx):
            # keep at true size so the route can enter/exit unobstructed.
            result.append((ox, oy, ow, oh))
        else:
            result.append((ox - margin, oy - margin, ow + 2.0 * margin, oh + 2.0 * margin))
    return result


def _route_avoiding_obstacles(
    sx: float,
    sy: float,
    tx: float,
    ty: float,
    obstacles: list[_Rect],
    total_height: float,
    *,
    gap: float = 4.0,
    margin: float = 0.0,
) -> list[tuple[float, float]]:
    """Route an edge orthogonally from ``(sx, sy)`` to ``(tx, ty)`` avoiding obstacles.

    Tries progressively more complex polylines until one clears every obstacle
    rectangle in *obstacles*:

    1. **Straight line** — when source and target share the same y and the
       path is obstacle-free.
    2. **Simple Z-route** (4 waypoints) — one vertical segment in the first
       free corridor that allows a clear horizontal return to the target.
    3. **Double-Z route** (6 waypoints) — uses two vertical corridors (one
       near the source, one near the target) bridged by a horizontal bypass
       level; the candidate closest to the midpoint of *sy* and *ty* is tried
       first so the detour is as short as possible.
    4. **Midpoint fallback** — when sy ≈ ty and no double-Z cleared, routes
       via the nearest bypass level to avoid collapsing to a straight line
       that would re-enter an obstacle.

    Args:
        sx: x-coordinate of the source port anchor (right edge of source node).
        sy: y-coordinate of the source port anchor.
        tx: x-coordinate of the target port anchor (left edge of target node).
        ty: y-coordinate of the target port anchor.
        obstacles: Axis-aligned rectangles ``(x, y, width, height)`` to avoid.
        total_height: Canvas height, used as an outer bound for bypass levels.
        gap: Additional clearance added above/below obstacles for bypass levels,
            on top of any inflation from *margin*.
        margin: Visual clearance maintained between routed segments and every
            box they do not need to enter.  Source and target nodes are exempt
            so that connection segments can reach their port anchors.

    Returns:
        An ordered list of ``(x, y)`` waypoints forming a valid orthogonal
        polyline (all segments are horizontal or vertical).
    """
    # Inflate all non-source/non-target obstacles by the visual margin so that
    # every subsequent corridor, clearance, and bypass calculation naturally
    # keeps routes at least *margin* layout units away from those boxes.
    # Inflation must happen before the sy ≈ ty check so the straight-line
    # candidate is evaluated against the same inflated geometry as all other
    # route attempts.
    obs = _inflate_obstacles(obstacles, sx, tx, margin)

    # Attempt 0: straight line — only when sy ≈ ty AND the path is clear.
    # Do not return unconditionally: after peripheral alignment sy can equal ty
    # exactly while an intermediate component sits on the same horizontal level,
    # making the straight line visually cross that component.
    if abs(sy - ty) < 0.5:
        wps: list[tuple[float, float]] = [(sx, sy), (tx, ty)]
        if _route_is_clear(wps, obs):
            return wps
        # Blocked — fall through so the double-Z finds a detour.

    cxs = _free_corridor_xs(sx, tx, obs)

    # Attempt 1: simple Z-route — find a corridor where the whole 3-segment
    # path clears every (inflated) obstacle.
    # When sy == ty every simple Z degenerates to the same blocked horizontal,
    # so these will all fail and control reaches the double-Z below.
    for cx in cxs:
        wps = [(sx, sy), (cx, sy), (cx, ty), (tx, ty)]
        if _route_is_clear(wps, obs):
            return wps

    # Attempt 2: double-Z route — first corridor for the vertical leg near the
    # source, last corridor for the vertical leg near the target, with a
    # horizontal bypass outside all intermediate obstacles.
    # Sort bypass candidates by distance from the midpoint of sy and ty so the
    # shortest detour is tried first.
    cx1 = cxs[0] if cxs else (sx + tx) / 2.0
    cx2 = cxs[-1] if cxs else (sx + tx) / 2.0
    mid_y = (sy + ty) / 2.0
    bypass_candidates = sorted(
        _bypass_levels(cx1, cx2, obs, total_height, gap),
        key=lambda by: abs(by - mid_y),
    )
    for by in bypass_candidates:
        if cx1 != cx2:
            wps = [(sx, sy), (cx1, sy), (cx1, by), (cx2, by), (cx2, ty), (tx, ty)]
        else:
            # Only one corridor: use a 5-segment U-shape.
            wps = [(sx, sy), (cx1, sy), (cx1, by), (tx, by), (tx, ty)]
        if _route_is_clear(wps, obs):
            return wps

    # Fallback: midpoint Z.  When sy ≈ ty this degenerates to a straight line,
    # so first try a bypass-based detour to keep the route obstacle-free.
    mid_x = (sx + tx) / 2.0
    if abs(sy - ty) < 0.5:
        for by in sorted(
            _bypass_levels(mid_x, mid_x, obs, total_height, gap),
            key=lambda by: abs(by - mid_y),
        ):
            wps = [(sx, sy), (mid_x, sy), (mid_x, by), (tx, by), (tx, ty)]
            if _route_is_clear(wps, obs):
                return wps
    return [(sx, sy), (mid_x, sy), (mid_x, ty), (tx, ty)]
