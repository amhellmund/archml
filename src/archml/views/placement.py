# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Placement algorithm for ArchML visualization diagrams.

Implements a Sugiyama-style hierarchical layout algorithm that produces a
backend-independent :class:`LayoutPlan` describing where to position every
element in a :class:`~archml.views.topology.VizDiagram`.

Algorithm overview
------------------
The algorithm operates in four phases, mirroring the classical Sugiyama
framework used by Graphviz *dot*:

1. **Layer assignment** — Internal child nodes are partitioned into horizontal
   columns using the *longest-path* algorithm.  Nodes that only initiate
   requests (edge sources, i.e. nodes whose ``requires`` ports appear as edge
   source ports) are placed in the leftmost column; nodes that only respond
   (edge sinks) are placed in the rightmost column.

2. **Crossing minimisation** — Nodes within each column are ordered to reduce
   the number of edge crossings using the *barycenter heuristic* with multiple
   alternating forward and backward sweep passes.

3. **Peripheral placement** — Nodes outside the root boundary (terminal nodes
   and external actors) are classified as *left* or *right* peripherals based
   on their role in the edge graph, and stacked vertically beside the boundary.

4. **Coordinate assignment** — Abstract float coordinates are assigned to every
   node and boundary.  Port anchors follow the ArchML convention: ``requires``
   ports are anchored to the **left edge** of their node (incoming connections),
   ``provides`` ports to the **right edge** (outgoing connections).  Edge routes
   are straight lines between the port anchors.

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
        boundary_padding: Padding between the root boundary edge and the
            nearest child node on each side.
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
            Currently contains the root boundary; nested boundaries will be
            added in future versions.
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
        A :class:`LayoutPlan` covering all nodes, the root boundary, all port
        anchors, and all resolvable edge routes.
    """
    return _Layouter(diagram, config or LayoutConfig()).run()


# ################
# Implementation
# ################


class _Layouter:
    """Stateful helper that runs the full Sugiyama layout pipeline."""

    def __init__(self, diagram: VizDiagram, cfg: LayoutConfig) -> None:
        self._diagram = diagram
        self._cfg = cfg

    def run(self) -> LayoutPlan:  # noqa: PLR0914 – intentionally wide orchestrator
        diagram = self._diagram
        cfg = self._cfg

        # --- Step 0: build port → node mapping ---
        port_to_node = _build_port_to_node(diagram)

        # --- Step 1: collect all leaf VizNodes and all nested VizBoundaries ---
        # Boundaries can be arbitrarily deep (e.g. A inside Order inside Architecture).
        # We flatten all leaf VizNode descendants into one list for layer assignment,
        # and track which leaf nodes belong to which boundary for bounding-box computation.
        child_nodes: list[VizNode] = [n for n in diagram.root.children if isinstance(n, VizNode)]
        all_nested_boundaries: list[VizBoundary] = _collect_all_nested_boundaries(diagram.root)
        boundary_inner_nodes: dict[str, list[VizNode]] = {}
        for bnd in all_nested_boundaries:
            leaf_nodes = _collect_leaf_nodes(bnd)
            boundary_inner_nodes[bnd.id] = leaf_nodes
            child_nodes.extend(leaf_nodes)
        # Deduplicate while preserving order (a leaf node belongs to exactly one boundary,
        # but collect_leaf_nodes is called per boundary so there are no actual duplicates).
        seen_node_ids: set[str] = set()
        deduped: list[VizNode] = []
        for n in child_nodes:
            if n.id not in seen_node_ids:
                seen_node_ids.add(n.id)
                deduped.append(n)
        child_nodes = deduped

        child_ids = {n.id for n in child_nodes}
        child_by_id = {n.id: n for n in child_nodes}

        # Build directed edge graph between child nodes.
        internal_edges: list[tuple[str, str]] = []
        for edge in diagram.edges:
            src = port_to_node.get(edge.source_port_id)
            tgt = port_to_node.get(edge.target_port_id)
            if src in child_ids and tgt in child_ids and src != tgt:
                internal_edges.append((src, tgt))

        # --- Step 2: layer assignment (longest-path) ---
        child_id_list = [n.id for n in child_nodes]
        raw_layers = _longest_path_layers(child_id_list, internal_edges)

        num_layers = max(raw_layers.values(), default=-1) + 1 if raw_layers else 0
        layer_groups: dict[int, list[str]] = defaultdict(list)
        for node_id, layer in raw_layers.items():
            layer_groups[layer].append(node_id)
        ordered_layers: list[list[str]] = [layer_groups.get(i, []) for i in range(num_layers)]

        # --- Step 3: crossing minimisation (barycenter heuristic) ---
        ordered_layers = _minimise_crossings(ordered_layers, internal_edges)

        # --- Step 4: classify peripheral nodes ---
        peripheral_left, peripheral_right = _classify_peripherals(diagram.peripheral_nodes, diagram.edges, port_to_node)

        # --- Step 5: compute effective node dimensions (text-aware) ---
        # Each category of nodes gets a single uniform size equal to the maximum
        # required width across all members of that category.
        node_w, node_h = _effective_inner_size(child_nodes, cfg)
        peri_w, peri_h = _effective_peripheral_size(diagram.peripheral_nodes, cfg)

        # --- Step 6: compute geometry ---
        max_per_layer = max((len(la) for la in ordered_layers), default=0)

        # Padding used on all sides of nested (child) boundaries.
        half_pad = cfg.boundary_padding * 0.75
        # Each nesting level adds a top extension of (half_pad + boundary_title_reserve)
        # because the inner boundary's top edge protrudes above its leaf nodes.
        # Multiply by the maximum nesting depth so all titles clear the outer title.
        # Each nesting level also adds a downward extension of half_pad below leaf nodes,
        # so the same depth factor is applied symmetrically at the bottom.
        nesting_depth = _max_boundary_depth(diagram.root)
        nested_upward_ext = nesting_depth * (half_pad + cfg.boundary_title_reserve)
        nested_downward_ext = nesting_depth * half_pad

        inner_w = num_layers * node_w + max(0, num_layers - 1) * cfg.layer_gap
        inner_h = max_per_layer * node_h + max(0, max_per_layer - 1) * cfg.node_gap
        boundary_w = inner_w + 2 * cfg.boundary_padding
        boundary_h = (
            inner_h + 2 * cfg.boundary_padding + cfg.boundary_title_reserve + nested_upward_ext + nested_downward_ext
        )

        left_h = _stack_height(len(peripheral_left), peri_h, cfg.node_gap)
        right_h = _stack_height(len(peripheral_right), peri_h, cfg.node_gap)

        total_h = max(boundary_h, left_h, right_h)

        left_zone_w = peri_w if peripheral_left else 0.0
        right_zone_w = peri_w if peripheral_right else 0.0
        left_gap = cfg.peripheral_gap if peripheral_left else 0.0
        right_gap = cfg.peripheral_gap if peripheral_right else 0.0

        boundary_x = left_zone_w + left_gap
        boundary_y = (total_h - boundary_h) / 2.0
        total_w = boundary_x + boundary_w + right_gap + right_zone_w

        # --- Step 7: assign node positions ---
        node_layouts: dict[str, NodeLayout] = {}

        for layer_idx, layer_node_ids in enumerate(ordered_layers):
            col_x = boundary_x + cfg.boundary_padding + layer_idx * (node_w + cfg.layer_gap)
            col_h = _stack_height(len(layer_node_ids), node_h, cfg.node_gap)
            col_start_y = (
                boundary_y
                + cfg.boundary_padding
                + cfg.boundary_title_reserve
                + nested_upward_ext
                + (inner_h - col_h) / 2.0
            )
            for row, node_id in enumerate(layer_node_ids):
                node_layouts[node_id] = NodeLayout(
                    node_id=node_id,
                    x=col_x,
                    y=col_start_y + row * (node_h + cfg.node_gap),
                    width=node_w,
                    height=node_h,
                )

        left_start_y = (total_h - left_h) / 2.0
        for i, node in enumerate(peripheral_left):
            node_layouts[node.id] = NodeLayout(
                node_id=node.id,
                x=0.0,
                y=left_start_y + i * (peri_h + cfg.node_gap),
                width=peri_w,
                height=peri_h,
            )

        right_x = boundary_x + boundary_w + right_gap
        right_start_y = (total_h - right_h) / 2.0
        for i, node in enumerate(peripheral_right):
            node_layouts[node.id] = NodeLayout(
                node_id=node.id,
                x=right_x,
                y=right_start_y + i * (peri_h + cfg.node_gap),
                width=peri_w,
                height=peri_h,
            )

        # --- Step 8: boundary layout ---
        boundary_layouts: dict[str, BoundaryLayout] = {
            diagram.root.id: BoundaryLayout(
                boundary_id=diagram.root.id,
                x=boundary_x,
                y=boundary_y,
                width=boundary_w,
                height=boundary_h,
            )
        }

        # Compute bounding-box layouts for all nested VizBoundary instances.
        # Process in reverse order (deepest-first) so that when we compute a parent
        # boundary's box we can also include its child boundaries' boxes.
        for bnd in reversed(all_nested_boundaries):
            inner_lays = [node_layouts[n.id] for n in boundary_inner_nodes[bnd.id] if n.id in node_layouts]
            # Also include any direct VizBoundary children already computed.
            for child in bnd.children:
                if isinstance(child, VizBoundary) and child.id in boundary_layouts:
                    bl = boundary_layouts[child.id]
                    # Represent child boundary as a pseudo NodeLayout for min/max.
                    inner_lays.append(NodeLayout(node_id=child.id, x=bl.x, y=bl.y, width=bl.width, height=bl.height))
            if not inner_lays:
                continue
            bnd_min_x = min(nl.x for nl in inner_lays)
            bnd_max_x = max(nl.x + nl.width for nl in inner_lays)
            bnd_min_y = min(nl.y for nl in inner_lays)
            bnd_max_y = max(nl.y + nl.height for nl in inner_lays)
            boundary_layouts[bnd.id] = BoundaryLayout(
                boundary_id=bnd.id,
                x=bnd_min_x - half_pad,
                y=bnd_min_y - half_pad - cfg.boundary_title_reserve,
                width=(bnd_max_x - bnd_min_x) + 2 * half_pad,
                height=(bnd_max_y - bnd_min_y) + 2 * half_pad + cfg.boundary_title_reserve,
            )

        # --- Step 9: port anchors ---
        port_anchors: dict[str, PortAnchor] = {}

        root_bl = boundary_layouts[diagram.root.id]
        _add_boundary_anchors(diagram.root, root_bl, port_anchors)

        all_viz_nodes: dict[str, VizNode] = {
            **child_by_id,
            **{n.id: n for n in diagram.peripheral_nodes},
        }
        for node_id, nl in node_layouts.items():
            viz_node = all_viz_nodes.get(node_id)
            if viz_node is not None:
                _add_node_anchors(viz_node, nl, port_anchors)

        # --- Step 10: edge routes (straight-line) ---
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


# -------- boundary traversal helpers --------


def _collect_all_nested_boundaries(boundary: VizBoundary) -> list[VizBoundary]:
    """Return all VizBoundary descendants of *boundary* in breadth-first order."""
    result: list[VizBoundary] = []
    queue = list(boundary.children)
    while queue:
        child = queue.pop(0)
        if isinstance(child, VizBoundary):
            result.append(child)
            queue.extend(child.children)
    return result


def _collect_leaf_nodes(boundary: VizBoundary) -> list[VizNode]:
    """Return all VizNode leaf descendants of *boundary* (recursive, depth-first)."""
    result: list[VizNode] = []
    for child in boundary.children:
        if isinstance(child, VizNode):
            result.append(child)
        else:
            result.extend(_collect_leaf_nodes(child))
    return result


def _max_boundary_depth(boundary: VizBoundary) -> int:
    """Return the maximum number of nested VizBoundary levels inside *boundary*."""
    max_d = 0
    for child in boundary.children:
        if isinstance(child, VizBoundary):
            max_d = max(max_d, 1 + _max_boundary_depth(child))
    return max_d


# -------- graph helpers --------


def _build_port_to_node(diagram: VizDiagram) -> dict[str, str]:
    """Return a mapping ``port_id → node_or_boundary_id`` for the whole diagram."""
    result: dict[str, str] = {}
    for p in diagram.root.ports:
        result[p.id] = diagram.root.id
    _collect_boundary_port_to_node(diagram.root, result)
    for node in diagram.peripheral_nodes:
        for p in node.ports:
            result[p.id] = node.id
    return result


def _collect_boundary_port_to_node(boundary: VizBoundary, out: dict[str, str]) -> None:
    """Recursively map ports of *boundary*'s children into *out*."""
    for child in boundary.children:
        if isinstance(child, VizNode):
            for p in child.ports:
                out[p.id] = child.id
        else:
            for p in child.ports:
                out[p.id] = child.id
            _collect_boundary_port_to_node(child, out)


def _classify_peripherals(
    peripheral_nodes: list[VizNode],
    edges: list,
    port_to_node: dict[str, str],
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
            # Mixed: use majority port direction as tiebreaker.
            req_count = sum(1 for p in node.ports if p.direction == "requires")
            prov_count = len(node.ports) - req_count
            if req_count >= prov_count:
                left.append(node)
            else:
                right.append(node)
        else:
            # No edges: terminal kind is authoritative.
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

    # Kahn's topological sort, tracking longest path simultaneously.
    layers: dict[str, int] = {}
    queue: deque[str] = deque()
    for n in node_ids:
        if in_degree[n] == 0:
            layers[n] = 0
            queue.append(n)

    if not queue:
        # All nodes are in cycles – assign every node to layer 0.
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

    # Nodes unreachable from sources (in cycles) get layer 0.
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
        if pass_num % 2 == 0:  # forward: order layer i by predecessors in i-1
            for i in range(1, len(result)):
                fixed = {node: pos for pos, node in enumerate(result[i - 1])}
                result[i] = _barycenter_sort(result[i], predecessors, fixed)
        else:  # backward: order layer i by successors in i+1
            for i in range(len(result) - 2, -1, -1):
                fixed = {node: pos for pos, node in enumerate(result[i + 1])}
                result[i] = _barycenter_sort(result[i], successors, fixed)

    return result


def _barycenter_sort(
    nodes: list[str],
    neighbors: dict[str, list[str]],
    positions: dict[str, int],
) -> list[str]:
    """Sort *nodes* by the average position of their neighbours in the fixed layer.

    Nodes with no neighbours in the fixed layer keep their relative order
    (they are sorted to the end, preserving stability via Python's stable sort).
    """

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
    """Minimum node height needed to fit two lines of text with an explicit gap.

    Accounts for the bold interface-name line, the explicit
    ``cfg.channel_line_gap``, the smaller channel-label line, and the total
    vertical padding ``cfg.node_v_padding``.
    """
    line1_h = cfg.font_size
    line2_h = cfg.font_size * cfg.channel_label_font_ratio
    return line1_h + cfg.channel_line_gap + line2_h + cfg.node_v_padding


def _effective_inner_size(nodes: list[VizNode], cfg: LayoutConfig) -> tuple[float, float]:
    """Return ``(width, height)`` for inner child nodes.

    Width is ``max(cfg.node_width, max_required_text_width)`` computed
    uniformly so every label fits.  Bold text (used for ``component`` and
    ``system`` node labels and for the interface-name line of ``channel``
    nodes) is estimated using ``cfg.bold_char_width_factor``.

    Height is ``max(cfg.node_height, _min_channel_node_height(cfg))`` when
    any channel node is present; otherwise ``cfg.node_height``.  This
    ensures both text lines and the explicit gap fit without clipping.
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
    """Return ``(width, height)`` for peripheral nodes.

    The width is ``max(cfg.peripheral_node_width, max_required_text_width)``
    so that every peripheral label fits.  Height is always
    ``cfg.peripheral_node_height``.
    """
    w = cfg.peripheral_node_width
    for node in nodes:
        needed = _required_text_width(node.label, cfg)
        w = max(w, needed)
    return w, cfg.peripheral_node_height


# -------- coordinate helpers --------


def _stack_height(count: int, item_h: float, gap: float) -> float:
    """Total height of *count* items stacked with *gap* between them."""
    if count <= 0:
        return 0.0
    return count * item_h + max(0, count - 1) * gap


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
