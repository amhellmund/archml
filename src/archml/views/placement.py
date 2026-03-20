# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Placement algorithm for ArchML visualization diagrams.

Implements a Sugiyama-style hierarchical layout algorithm that produces a
backend-independent :class:`LayoutPlan` describing where to position every
element in a :class:`~archml.views.topology.VizDiagram`.

Algorithm overview
------------------
The algorithm operates recursively, one boundary level at a time:

1. **Recursive content sizing** — For each :class:`VizBoundary` in the tree,
   compute the layout of its *direct* children first (bottom-up).  Direct
   children are either opaque :class:`VizNode` instances or nested
   :class:`VizBoundary` instances whose size is already known from the
   recursive step.  This ensures each boundary is treated as a single,
   correctly-sized unit in its parent's layout.

2. **Layer assignment** — Direct child nodes are partitioned into horizontal
   columns using the *longest-path* algorithm applied only to the edges that
   connect children at this level (not cross-boundary edges from deeper
   levels).

3. **Crossing minimisation** — Nodes within each column are ordered to reduce
   the number of edge crossings using the *barycenter heuristic* with multiple
   alternating forward and backward sweep passes.

4. **Peripheral placement** — Nodes outside the root boundary (terminal nodes
   and external actors) are classified as *left* or *right* peripherals based
   on their role in the edge graph, and stacked vertically beside the boundary.

5. **Coordinate assignment** — Relative positions within each boundary are
   computed, then converted to absolute coordinates top-down.  Port anchors
   follow the ArchML convention: ``requires`` ports are anchored to the
   **left edge** of their node (incoming connections), ``provides`` ports to
   the **right edge** (outgoing connections).  Edge routes are straight lines
   between the port anchors.

Output
------
The resulting :class:`LayoutPlan` is fully independent of any rendering
backend (SVG, Dash, etc.).  All coordinates are expressed in abstract *layout
units*.  Renderers multiply these by their chosen scale factor to obtain pixel
or viewport coordinates.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from archml.views.topology import VizBoundary, VizDiagram, VizNode, VizPort

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
        diagram_margin: Uniform whitespace added around the entire diagram on
            all four sides (layout units).  Prevents box strokes from being
            clipped at the SVG/PNG canvas edge when there are no peripheral
            nodes on a given side.
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
    diagram_margin: float = 4.0


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
    target port anchor.  Additional interior waypoints may be added by more
    sophisticated routing passes; the base implementation uses straight lines
    (two waypoints only).

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


def compute_layout(
    diagram: VizDiagram,
    *,
    config: LayoutConfig | None = None,
) -> LayoutPlan:
    """Compute a :class:`LayoutPlan` for *diagram*.

    Applies the Sugiyama-style hierarchical layout algorithm described in this
    module's docstring.  The returned plan is fully independent of any rendering
    backend.

    Args:
        diagram: The topology to lay out, as produced by
            :func:`~archml.views.topology.build_viz_diagram`.
        config: Optional layout configuration.  Defaults to
            :class:`LayoutConfig` with standard values if omitted.

    Returns:
        A :class:`LayoutPlan` covering all nodes, all boundaries, all port
        anchors, and all resolvable edge routes.
    """
    return _Layouter(diagram, config or LayoutConfig()).run()


# ################
# Implementation
# ################


@dataclass
class _BndLayoutResult:
    """Pre-computed layout of a boundary's direct children in relative coordinates.

    Relative coordinates have their origin at the top-left of the boundary's
    interior area (i.e. after applying ``boundary_padding`` and
    ``boundary_title_reserve`` offsets from the boundary's own top-left corner).
    """

    content_w: float
    content_h: float
    # (rel_x, rel_y, width, height) for each direct child
    child_rects: dict[str, tuple[float, float, float, float]]
    # Recursive layout results for any VizBoundary children
    sub_layouts: dict[str, _BndLayoutResult]


class _Layouter:
    """Stateful helper that runs the full layout pipeline."""

    def __init__(self, diagram: VizDiagram, cfg: LayoutConfig) -> None:
        self._diagram = diagram
        self._cfg = cfg

    def run(self) -> LayoutPlan:
        diagram = self._diagram
        cfg = self._cfg

        # --- Step 1: classify peripheral nodes ---
        peripheral_left, peripheral_right = _classify_peripherals(diagram.peripheral_nodes, diagram.edges)
        peri_w, peri_h = _effective_peripheral_size(diagram.peripheral_nodes, cfg)

        # --- Step 2: compute root boundary content layout (recursive) ---
        root_content = _compute_bnd_layout(diagram.root, cfg, diagram.edges)
        boundary_w = root_content.content_w + 2 * cfg.boundary_padding
        boundary_h = root_content.content_h + 2 * cfg.boundary_padding + cfg.boundary_title_reserve

        left_h = _stack_height(len(peripheral_left), peri_h, cfg.node_gap)
        right_h = _stack_height(len(peripheral_right), peri_h, cfg.node_gap)
        content_h = max(boundary_h, left_h, right_h)

        left_zone_w = (peri_w + cfg.peripheral_gap) if peripheral_left else 0.0
        right_zone_w = (peri_w + cfg.peripheral_gap) if peripheral_right else 0.0

        margin = cfg.diagram_margin
        boundary_x = margin + left_zone_w
        boundary_y = margin + (content_h - boundary_h) / 2.0
        total_w = left_zone_w + boundary_w + right_zone_w + 2 * margin
        total_h = content_h + 2 * margin

        # --- Step 3: assign absolute positions ---
        node_layouts: dict[str, NodeLayout] = {}
        boundary_layouts: dict[str, BoundaryLayout] = {}
        port_anchors: dict[str, PortAnchor] = {}

        root_bl = BoundaryLayout(
            boundary_id=diagram.root.id,
            x=boundary_x,
            y=boundary_y,
            width=boundary_w,
            height=boundary_h,
        )
        boundary_layouts[diagram.root.id] = root_bl
        _add_boundary_anchors(diagram.root, root_bl, port_anchors)

        _materialize_content(
            diagram.root,
            root_content,
            boundary_x + cfg.boundary_padding,
            boundary_y + cfg.boundary_padding + cfg.boundary_title_reserve,
            cfg,
            node_layouts,
            boundary_layouts,
            port_anchors,
        )

        # --- Step 4: place peripheral nodes ---
        left_start_y = margin + (content_h - left_h) / 2.0
        for i, node in enumerate(peripheral_left):
            nl = NodeLayout(
                node_id=node.id,
                x=margin,
                y=left_start_y + i * (peri_h + cfg.node_gap),
                width=peri_w,
                height=peri_h,
            )
            node_layouts[node.id] = nl
            _add_node_anchors(node, nl, port_anchors)

        right_x = boundary_x + boundary_w + (cfg.peripheral_gap if peripheral_right else 0.0)
        right_start_y = margin + (content_h - right_h) / 2.0
        for i, node in enumerate(peripheral_right):
            nl = NodeLayout(
                node_id=node.id,
                x=right_x,
                y=right_start_y + i * (peri_h + cfg.node_gap),
                width=peri_w,
                height=peri_h,
            )
            node_layouts[node.id] = nl
            _add_node_anchors(node, nl, port_anchors)

        # --- Step 5: edge routes (straight-line) ---
        edge_routes: dict[str, EdgeRoute] = {}
        for edge in diagram.edges:
            src_anc = port_anchors.get(edge.source_port_id)
            tgt_anc = port_anchors.get(edge.target_port_id)
            if src_anc is not None and tgt_anc is not None:
                edge_routes[edge.id] = EdgeRoute(
                    edge_id=edge.id,
                    waypoints=[(src_anc.x, src_anc.y), (tgt_anc.x, tgt_anc.y)],
                )

        return LayoutPlan(
            diagram_id=diagram.id,
            total_width=total_w,
            total_height=total_h,
            nodes=node_layouts,
            boundaries=boundary_layouts,
            port_anchors=port_anchors,
            edge_routes=edge_routes,
        )


# -------- recursive boundary layout --------


def _compute_bnd_layout(
    boundary: VizBoundary,
    cfg: LayoutConfig,
    all_edges: list,
) -> _BndLayoutResult:
    """Compute the relative layout for *boundary*'s direct children.

    Works recursively: nested :class:`VizBoundary` children are laid out first
    so their dimensions are known before the parent arranges its columns.
    Only edges that connect ports belonging to direct children at this level
    are used for layer assignment — edges to/from deeper descendants are not
    considered at this level.

    Args:
        boundary: The boundary whose children are to be laid out.
        cfg: Layout configuration.
        all_edges: All edges in the diagram (filtered to this level via
            the direct-child port mapping).

    Returns:
        A :class:`_BndLayoutResult` with relative child positions and sizes.
    """
    direct_children = boundary.children
    if not direct_children:
        return _BndLayoutResult(content_w=0.0, content_h=0.0, child_rects={}, sub_layouts={})

    # Map every port in this boundary's subtree to the direct child that owns it.
    # This ensures edges to/from nested inner nodes are attributed to the right
    # direct-child boundary, not to the inner node itself.
    port_to_direct = _build_port_to_direct_child(boundary)
    direct_ids = {c.id for c in direct_children}

    # Build edge graph between direct children only.
    internal_edges: list[tuple[str, str]] = []
    for edge in all_edges:
        src = port_to_direct.get(edge.source_port_id)
        tgt = port_to_direct.get(edge.target_port_id)
        if src is not None and tgt is not None and src in direct_ids and tgt in direct_ids and src != tgt:
            internal_edges.append((src, tgt))

    # Recursively compute sub-layouts for nested VizBoundary children.
    sub_layouts: dict[str, _BndLayoutResult] = {}
    for child in direct_children:
        if isinstance(child, VizBoundary):
            sub_layouts[child.id] = _compute_bnd_layout(child, cfg, all_edges)

    # Compute uniform size for direct VizNode children.
    viz_nodes = [c for c in direct_children if isinstance(c, VizNode)]
    node_w, node_h = _effective_inner_size(viz_nodes, cfg) if viz_nodes else (cfg.node_width, cfg.node_height)

    # Determine each child's size.
    child_sizes: dict[str, tuple[float, float]] = {}
    for child in direct_children:
        if isinstance(child, VizNode):
            child_sizes[child.id] = (node_w, node_h)
        else:
            sub = sub_layouts[child.id]
            bnd_w = sub.content_w + 2 * cfg.boundary_padding
            bnd_h = sub.content_h + 2 * cfg.boundary_padding + cfg.boundary_title_reserve
            child_sizes[child.id] = (bnd_w, bnd_h)

    # Layer assignment.
    child_id_list = [c.id for c in direct_children]
    raw_layers = _longest_path_layers(child_id_list, internal_edges)
    num_layers = max(raw_layers.values(), default=-1) + 1 if raw_layers else 0

    if num_layers == 0:
        ordered_layers: list[list[str]] = [child_id_list]
        num_layers = 1
    else:
        layer_groups: dict[int, list[str]] = defaultdict(list)
        for cid, layer in raw_layers.items():
            layer_groups[layer].append(cid)
        ordered_layers = [layer_groups.get(i, []) for i in range(num_layers)]

    # Crossing minimisation.
    ordered_layers = _minimise_crossings(ordered_layers, internal_edges)

    # Compute column widths and heights.
    col_widths = [max((child_sizes[cid][0] for cid in col), default=0.0) for col in ordered_layers]
    col_heights = [_stack_height_variable([child_sizes[cid][1] for cid in col], cfg.node_gap) for col in ordered_layers]

    content_w = sum(col_widths) + max(0, num_layers - 1) * cfg.layer_gap
    content_h = max(col_heights, default=0.0)

    # Assign relative positions (origin = interior top-left of this boundary).
    child_rects: dict[str, tuple[float, float, float, float]] = {}
    col_x = 0.0
    for col, col_w, col_h in zip(ordered_layers, col_widths, col_heights, strict=True):
        row_y = (content_h - col_h) / 2.0
        for cid in col:
            cw, ch = child_sizes[cid]
            x = col_x + (col_w - cw) / 2.0
            child_rects[cid] = (x, row_y, cw, ch)
            row_y += ch + cfg.node_gap
        col_x += col_w + cfg.layer_gap

    return _BndLayoutResult(
        content_w=content_w,
        content_h=content_h,
        child_rects=child_rects,
        sub_layouts=sub_layouts,
    )


def _materialize_content(
    boundary: VizBoundary,
    content: _BndLayoutResult,
    origin_x: float,
    origin_y: float,
    cfg: LayoutConfig,
    node_layouts: dict[str, NodeLayout],
    boundary_layouts: dict[str, BoundaryLayout],
    port_anchors: dict[str, PortAnchor],
) -> None:
    """Convert relative positions in *content* to absolute layout positions.

    Recursively descends into nested :class:`VizBoundary` children, translating
    their relative coordinates by the parent's absolute origin.
    """
    for child in boundary.children:
        rect = content.child_rects.get(child.id)
        if rect is None:
            continue
        rx, ry, rw, rh = rect
        abs_x = origin_x + rx
        abs_y = origin_y + ry

        if isinstance(child, VizNode):
            nl = NodeLayout(node_id=child.id, x=abs_x, y=abs_y, width=rw, height=rh)
            node_layouts[child.id] = nl
            _add_node_anchors(child, nl, port_anchors)
        else:
            bl = BoundaryLayout(boundary_id=child.id, x=abs_x, y=abs_y, width=rw, height=rh)
            boundary_layouts[child.id] = bl
            _add_boundary_anchors(child, bl, port_anchors)
            sub = content.sub_layouts.get(child.id)
            if sub is not None:
                _materialize_content(
                    child,
                    sub,
                    abs_x + cfg.boundary_padding,
                    abs_y + cfg.boundary_padding + cfg.boundary_title_reserve,
                    cfg,
                    node_layouts,
                    boundary_layouts,
                    port_anchors,
                )


# -------- port mapping helpers --------


def _build_port_to_direct_child(boundary: VizBoundary) -> dict[str, str]:
    """Map every port in *boundary*'s subtree to the direct child that contains it."""
    result: dict[str, str] = {}
    for child in boundary.children:
        _map_subtree_ports_to(child, child.id, result)
    return result


def _map_subtree_ports_to(
    node: VizNode | VizBoundary,
    target_id: str,
    out: dict[str, str],
) -> None:
    """Recursively map all ports in *node*'s subtree to *target_id*."""
    for p in node.ports:
        out[p.id] = target_id
    if isinstance(node, VizBoundary):
        for child in node.children:
            _map_subtree_ports_to(child, target_id, out)


# -------- peripheral classification --------


def _classify_peripherals(
    peripheral_nodes: list[VizNode],
    edges: list,
) -> tuple[list[VizNode], list[VizNode]]:
    """Classify peripheral nodes as left (source) or right (sink).

    A peripheral node is *left* if it acts as an edge source (its ports appear
    as ``source_port_id`` in edges, meaning it initiates requests rightward
    into the boundary).  It is *right* if it acts as an edge target (its ports
    appear as ``target_port_id``, meaning it receives requests from the
    boundary).  Ties and unconnected nodes fall back to port direction.
    """
    source_port_ids = {e.source_port_id for e in edges}
    target_port_ids = {e.target_port_id for e in edges}

    left: list[VizNode] = []
    right: list[VizNode] = []

    for node in peripheral_nodes:
        node_port_ids = {p.id for p in node.ports}
        is_src = bool(node_port_ids & source_port_ids)
        is_tgt = bool(node_port_ids & target_port_ids)

        if is_src and not is_tgt:
            left.append(node)
        elif is_tgt and not is_src:
            right.append(node)
        elif is_src and is_tgt:
            req_count = sum(1 for p in node.ports if p.direction == "requires")
            prov_count = len(node.ports) - req_count
            if req_count >= prov_count:
                left.append(node)
            else:
                right.append(node)
        else:
            has_req = any(p.direction == "requires" for p in node.ports)
            if has_req:
                left.append(node)
            else:
                right.append(node)

    return left, right


# -------- layer assignment --------


def _longest_path_layers(
    node_ids: list[str],
    edges: list[tuple[str, str]],
) -> dict[str, int]:
    """Assign a layer index to each node using the longest-path algorithm.

    Nodes with no incoming edges (sources) are assigned layer 0.  Each
    subsequent node is placed one layer after the deepest of its predecessors.
    This produces the minimum-height layering for a DAG.

    Cycles (which should not appear in valid ArchML models) are handled
    gracefully: any node that cannot be reached from a source is assigned
    layer 0.

    Args:
        node_ids: All node identifiers to be layered.
        edges: Directed edges as ``(source_id, target_id)`` pairs.  Only
            edges whose both endpoints are in *node_ids* are considered.

    Returns:
        Mapping from node ID to its layer index (0 = leftmost).
    """
    node_set = set(node_ids)
    successors: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {n: 0 for n in node_ids}

    for src, tgt in edges:
        if src in node_set and tgt in node_set and src != tgt:
            successors[src].append(tgt)
            in_degree[tgt] += 1

    layers: dict[str, int] = {}
    queue: deque[str] = deque()
    for n in node_ids:
        if in_degree[n] == 0:
            layers[n] = 0
            queue.append(n)

    if not queue:
        return {n: 0 for n in node_ids}

    while queue:
        curr = queue.popleft()
        curr_layer = layers[curr]
        for succ in successors[curr]:
            candidate = curr_layer + 1
            if succ not in layers or layers[succ] < candidate:
                layers[succ] = candidate
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    for n in node_ids:
        if n not in layers:
            layers[n] = 0

    return layers


# -------- crossing minimisation --------


def _minimise_crossings(
    layers: list[list[str]],
    edges: list[tuple[str, str]],
    num_passes: int = 4,
) -> list[list[str]]:
    """Reduce edge crossings using the barycenter heuristic.

    Performs *num_passes* alternating forward and backward sweeps.  In each
    forward sweep the nodes in layer *i* are reordered by the average position
    of their predecessors in layer *i − 1*.  Backward sweeps do the same in
    the opposite direction using successors.

    Args:
        layers: Current column-by-column node ordering (modified in place).
        edges: Directed edges as ``(source_id, target_id)`` pairs.
        num_passes: Number of alternating sweep passes (default 4).

    Returns:
        New layer ordering with reduced crossings.
    """
    if len(layers) <= 1:
        return layers

    successors: dict[str, list[str]] = defaultdict(list)
    predecessors: dict[str, list[str]] = defaultdict(list)
    for src, tgt in edges:
        successors[src].append(tgt)
        predecessors[tgt].append(src)

    result = [list(la) for la in layers]

    for pass_num in range(num_passes):
        if pass_num % 2 == 0:
            for i in range(1, len(result)):
                fixed = {node: pos for pos, node in enumerate(result[i - 1])}
                result[i] = _barycenter_sort(result[i], predecessors, fixed)
        else:
            for i in range(len(result) - 2, -1, -1):
                fixed = {node: pos for pos, node in enumerate(result[i + 1])}
                result[i] = _barycenter_sort(result[i], successors, fixed)

    return result


def _barycenter_sort(
    nodes: list[str],
    neighbors: dict[str, list[str]],
    positions: dict[str, int],
) -> list[str]:
    """Sort *nodes* by the average position of their neighbours in the fixed layer."""

    def _key(node_id: str) -> float:
        nbrs = [positions[nb] for nb in neighbors[node_id] if nb in positions]
        return sum(nbrs) / len(nbrs) if nbrs else float(len(positions))

    return sorted(nodes, key=_key)


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
        else:
            needed = _required_text_width(node.label, cfg)
        w = max(w, needed)
    return w, h


def _effective_peripheral_size(nodes: list[VizNode], cfg: LayoutConfig) -> tuple[float, float]:
    """Return ``(width, height)`` for peripheral nodes."""
    w = cfg.peripheral_node_width
    for node in nodes:
        needed = _required_text_width(node.label, cfg)
        w = max(w, needed)
    return w, cfg.peripheral_node_height


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
