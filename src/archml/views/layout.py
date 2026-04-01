# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Graphviz-based layout backend for ArchML diagrams.

Uses the ``dot`` command-line tool (Graphviz) to determine node and boundary
positions, then applies the same port-anchor and obstacle-aware edge-routing
logic as the built-in Sugiyama layout.

Requirements
------------
The ``dot`` executable must be on ``PATH`` (e.g. ``apt install graphviz`` /
``brew install graphviz``).  No additional Python packages are required.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from archml.views.placement import (
    BoundaryLayout,
    EdgeRoute,
    LayoutConfig,
    LayoutPlan,
    NodeLayout,
    PortAnchor,
    _add_boundary_anchors,
    _add_node_anchors,
    _effective_inner_size,
    _effective_peripheral_size,
    _route_avoiding_obstacles,
)
from archml.views.topology import VizBoundary, VizDiagram, VizNode

# ###############
# Public Interface
# ###############

_DOT_SCALE = 72.0  # Graphviz uses inches; 1 layout unit = 1 pt = 1/72 inch


def compute_layout(
    diagram: VizDiagram,
    *,
    config: LayoutConfig | None = None,
) -> LayoutPlan:
    """Compute a :class:`~archml.views.placement.LayoutPlan` using Graphviz ``dot``.

    Raises:
        RuntimeError: If the ``dot`` executable is not found or exits with an error.
    """
    cfg = config or LayoutConfig()
    dot_src = _build_dot(diagram, cfg)
    gv_json = _run_dot(dot_src)
    return _parse_to_plan(diagram, gv_json, cfg)


# ################
# Implementation
# ################


@dataclass
class _GvNode:
    gv_id: str
    cx: float  # centre x, layout units
    cy: float  # centre y (already flipped to top-left origin)
    width: float
    height: float


@dataclass
class _GvBoundary:
    gv_id: str
    x: float  # top-left
    y: float
    width: float
    height: float


def _collect_inner_nodes(boundary: VizBoundary) -> list[VizNode]:
    """Return all leaf :class:`VizNode` children from *boundary* recursively."""
    result: list[VizNode] = []
    for child in boundary.children:
        if isinstance(child, VizNode):
            result.append(child)
        else:
            result.extend(_collect_inner_nodes(child))
    return result


def _dot_id(raw: str) -> str:
    """Return *raw* wrapped as a quoted DOT identifier.

    DOT double-quoted strings accept any character, so this safely handles
    IDs containing ``/``, ``:``, spaces, or other special characters.
    Graphviz strips the surrounding quotes in JSON output, so lookups against
    the parsed JSON must use the raw (unquoted) string.
    """
    escaped = raw.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _collect_ports(boundary: VizBoundary) -> dict[str, str]:
    """Map every port_id in the boundary tree to its owner node/boundary id."""
    result: dict[str, str] = {}
    for port in boundary.ports:
        result[port.id] = boundary.id
    for child in boundary.children:
        if isinstance(child, VizNode):
            for port in child.ports:
                result[port.id] = child.id
        else:
            result.update(_collect_ports(child))
    return result


def _collect_node_parents(boundary: VizBoundary) -> dict[str, str]:
    """Map every leaf VizNode id to its immediate parent boundary id."""
    result: dict[str, str] = {}
    for child in boundary.children:
        if isinstance(child, VizNode):
            result[child.id] = boundary.id
        else:
            result.update(_collect_node_parents(child))
    return result


def _collect_boundary_ids(boundary: VizBoundary) -> set[str]:
    """Return the ids of *boundary* and all descendant boundaries."""
    result: set[str] = {boundary.id}
    for child in boundary.children:
        if isinstance(child, VizBoundary):
            result.update(_collect_boundary_ids(child))
    return result


# Prefix used for invisible phantom nodes anchored inside clusters so that
# edges can connect to clusters via lhead/ltail (requires compound=true).
_PHANTOM_PREFIX = "__ph__"


def _phantom_id(boundary_id: str) -> str:
    return f"{_PHANTOM_PREFIX}{boundary_id}"


def _write_cluster(
    boundary: VizBoundary,
    cfg: LayoutConfig,
    node_w_in: float,
    node_h_in: float,
    lines: list[str],
    indent: str = "  ",
    phantom_boundaries: set[str] | None = None,
) -> None:
    """Recursively emit a ``cluster_*`` subgraph for *boundary*.

    *node_w_in* and *node_h_in* are the pre-computed uniform node dimensions
    in Graphviz inches, matching the sizes produced by
    :func:`~archml.views.placement._effective_inner_size`.

    The cluster carries a ``label`` so Graphviz automatically reserves space
    for the boundary title at the top of the bounding box.  ``fontsize`` is
    set to match the renderer's boundary-title font so the reserved height
    is accurate.  The ``margin`` uses the two-value ``"horizontal,vertical"``
    format that Graphviz actually supports.

    When *phantom_boundaries* contains this boundary's id, an invisible
    zero-size phantom node is inserted so that ``lhead``/``ltail`` edges can
    anchor to the cluster (Graphviz requires a real node inside the cluster
    when ``compound=true`` is used).
    """
    cluster_name = _dot_id(f"cluster_{boundary.id}")
    # Cluster margin is in points (= layout units), NOT inches — unlike nodesep/ranksep/width/height.
    pad_pts = cfg.boundary_padding
    title_font_pts = cfg.font_size * cfg.boundary_title_font_ratio
    label = _dot_id(boundary.title or boundary.label)
    lines.append(f"{indent}subgraph {cluster_name} {{")
    lines.append(
        f'{indent}  graph [label={label},labelloc="t",fontsize="{title_font_pts:.1f}",margin="{pad_pts:.2f}"];'
    )
    if phantom_boundaries and boundary.id in phantom_boundaries:
        pid = _dot_id(_phantom_id(boundary.id))
        # Empty clusters (no real children) need a non-zero phantom so Graphviz
        # gives the cluster a usable bounding box; otherwise only the label is
        # measured and the box is far too short.
        if boundary.children:
            lines.append(f"{indent}  {pid} [style=invis,width=0,height=0,fixedsize=true];")
        else:
            lines.append(
                f'{indent}  {pid} [style=invis,width="{node_w_in:.4f}",height="{node_h_in:.4f}",fixedsize=true];'
            )
    elif not boundary.children:
        # Empty cluster not used as an edge endpoint: still needs a placeholder
        # node so Graphviz produces a usable bounding box (e.g. `system Foo {}`).
        pid = _dot_id(f"__empty__{boundary.id}")
        lines.append(f'{indent}  {pid} [style=invis,width="{node_w_in:.4f}",height="{node_h_in:.4f}",fixedsize=true];')
    for child in boundary.children:
        if isinstance(child, VizNode):
            nid = _dot_id(child.id)
            lines.append(
                f'{indent}  {nid} [width="{node_w_in:.4f}",height="{node_h_in:.4f}",fixedsize=true,shape=box,label=""];'
            )
        else:
            _write_cluster(child, cfg, node_w_in, node_h_in, lines, indent + "  ", phantom_boundaries)
    lines.append(f"{indent}}}")


def _build_dot(diagram: VizDiagram, cfg: LayoutConfig) -> str:
    """Build a DOT source string representing *diagram*."""
    ns_in = cfg.node_gap / _DOT_SCALE
    rs_in = cfg.layer_gap / _DOT_SCALE
    pg_in = cfg.peripheral_gap / _DOT_SCALE

    # Compute uniform node sizes using the same logic as the Sugiyama layout so
    # the rendered boxes are identically sized regardless of which layout engine
    # is used.
    inner_nodes = _collect_inner_nodes(diagram.root)
    inner_w, inner_h = _effective_inner_size(inner_nodes, cfg) if inner_nodes else (cfg.node_width, cfg.node_height)
    peri_w, peri_h = _effective_peripheral_size(diagram.peripheral_nodes, cfg)
    inner_w_in = inner_w / _DOT_SCALE
    inner_h_in = inner_h / _DOT_SCALE
    peri_w_in = peri_w / _DOT_SCALE
    peri_h_in = peri_h / _DOT_SCALE

    # Build port→owner map, parent-cluster map, boundary set, and peripheral set
    port_to_owner = _collect_ports(diagram.root)
    node_parent = _collect_node_parents(diagram.root)
    boundary_ids = _collect_boundary_ids(diagram.root)
    for node in diagram.peripheral_nodes:
        for port in node.ports:
            port_to_owner[port.id] = node.id
        node_parent[node.id] = "__peripheral__"

    # Determine which boundaries are used directly as edge endpoints so we can
    # insert phantom nodes for lhead/ltail anchoring (e.g. depth=0 diagrams
    # where the root system has no inner children but has boundary ports).
    phantom_boundaries: set[str] = set()
    for edge in diagram.edges:
        src_owner = port_to_owner.get(edge.source_port_id)
        tgt_owner = port_to_owner.get(edge.target_port_id)
        if src_owner in boundary_ids:
            phantom_boundaries.add(src_owner)
        if tgt_owner in boundary_ids:
            phantom_boundaries.add(tgt_owner)

    # Build DOT source now that phantom_boundaries is known
    lines: list[str] = []
    lines.append("digraph G {")
    lines.append("  rankdir=LR;")
    lines.append("  compound=true;")
    lines.append(f'  graph [nodesep="{ns_in:.4f}",ranksep="{rs_in:.4f}",pad="{pg_in:.4f}"];')
    lines.append('  node [shape=box,fixedsize=true,label=""];')
    _write_cluster(diagram.root, cfg, inner_w_in, inner_h_in, lines, "  ", phantom_boundaries)
    for node in diagram.peripheral_nodes:
        nid = _dot_id(node.id)
        lines.append(f'  {nid} [width="{peri_w_in:.4f}",height="{peri_h_in:.4f}",fixedsize=true,shape=box,label=""];')

    # Map phantom node ids to their parent boundary ids for minlen computation
    for bid in phantom_boundaries:
        node_parent[_phantom_id(bid)] = bid

    peripheral_ids = {node.id for node in diagram.peripheral_nodes}
    for edge in diagram.edges:
        src_owner = port_to_owner.get(edge.source_port_id)
        tgt_owner = port_to_owner.get(edge.target_port_id)
        if src_owner and tgt_owner and src_owner != tgt_owner:
            # Resolve boundary owners to their phantom node + lhead/ltail attrs
            if src_owner in boundary_ids:
                sid = _dot_id(_phantom_id(src_owner))
                ltail = f",ltail={_dot_id(f'cluster_{src_owner}')}"
                src_for_minlen = _phantom_id(src_owner)
            else:
                sid = _dot_id(src_owner)
                ltail = ""
                src_for_minlen = src_owner
            if tgt_owner in boundary_ids:
                tid = _dot_id(_phantom_id(tgt_owner))
                lhead = f",lhead={_dot_id(f'cluster_{tgt_owner}')}"
                tgt_for_minlen = _phantom_id(tgt_owner)
            else:
                tid = _dot_id(tgt_owner)
                lhead = ""
                tgt_for_minlen = tgt_owner
            eid = _dot_id(edge.id)
            # minlen=3: peripheral node (outside root cluster) ↔ inner node
            # minlen=2: cross-cluster edge (nodes in different immediate parent clusters)
            # minlen=1: intra-cluster siblings
            if src_for_minlen in peripheral_ids or tgt_for_minlen in peripheral_ids:
                minlen = 3
            elif node_parent.get(src_for_minlen) != node_parent.get(tgt_for_minlen):
                minlen = 2
            else:
                minlen = 1
            lines.append(f"  {sid} -> {tid} [id={eid},minlen={minlen}{ltail}{lhead}];")

    lines.append("}")
    return "\n".join(lines)


def _run_dot(dot_src: str) -> dict:
    """Run ``dot -Tjson`` and return the parsed JSON dict."""
    try:
        result = subprocess.run(
            ["dot", "-Tjson"],
            input=dot_src,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Graphviz 'dot' executable not found. "
            "Install Graphviz (e.g. 'apt install graphviz' or 'brew install graphviz')."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Graphviz dot failed:\n{exc.stderr}") from exc
    return json.loads(result.stdout)


def _sample_cubic_bezier(
    p0: list[float],
    p1: list[float],
    p2: list[float],
    p3: list[float],
    n: int = 8,
) -> list[tuple[float, float]]:
    """Return *n*+1 points sampled uniformly along the cubic Bezier P0–P3."""
    pts: list[tuple[float, float]] = []
    for i in range(n + 1):
        t = i / n
        mt = 1.0 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def _gv_edge_waypoints(
    draw_ops: list[dict],
    pos_str: str,
    canvas_h: float,
) -> list[tuple[float, float]] | None:
    """Convert Graphviz edge drawing instructions into flipped-y waypoints.

    Uses the ``"b"`` (B-spline) operation from *draw_ops* for the curve body
    and the ``e,x,y`` prefix of *pos_str* for the arrowhead endpoint.
    Returns ``None`` when the required data is absent.
    """
    # Arrowhead tip from the pos string ("e,x,y ..." format).
    endpoint: tuple[float, float] | None = None
    if pos_str.startswith("e,"):
        raw = pos_str.split(" ", 1)[0][2:]
        ex, ey = raw.split(",")
        endpoint = (float(ex), canvas_h - float(ey))

    # B-spline control points from the draw operations.
    ctrl: list[list[float]] = []
    for op in draw_ops:
        if op.get("op") == "b":
            ctrl = op["points"]
            break
    if not ctrl:
        return None

    # ctrl has 1 + 3*N points for N cubic Bezier segments.
    n_segs = (len(ctrl) - 1) // 3
    waypoints: list[tuple[float, float]] = []
    for seg in range(n_segs):
        i = seg * 3
        pts = _sample_cubic_bezier(ctrl[i], ctrl[i + 1], ctrl[i + 2], ctrl[i + 3])
        # Skip the shared start point for every segment after the first.
        if seg > 0:
            pts = pts[1:]
        waypoints.extend(pts)

    # Flip y to top-left origin.
    waypoints = [(x, canvas_h - y) for x, y in waypoints]

    if endpoint is not None:
        waypoints.append(endpoint)

    return waypoints if waypoints else None


def _parse_bb(bb: str) -> tuple[float, float, float, float]:
    """Parse a Graphviz ``bb`` string ``"x0,y0,x1,y1"`` → (x0, y0, x1, y1)."""
    parts = [float(v) for v in bb.split(",")]
    return parts[0], parts[1], parts[2], parts[3]


def _parse_pos(pos: str) -> tuple[float, float]:
    """Parse a Graphviz ``pos`` string ``"x,y"`` → (x, y)."""
    x, y = pos.split(",")
    return float(x), float(y)


def _parse_to_plan(diagram: VizDiagram, gv: dict, cfg: LayoutConfig) -> LayoutPlan:  # noqa: C901
    """Convert a Graphviz JSON output dict into a :class:`LayoutPlan`."""
    # Overall bounding box → total dimensions and y-flip offset
    bb = gv.get("bb", "")
    if not bb:
        raise RuntimeError("Graphviz output missing 'bb' attribute.")
    _, bb_y0, total_w, total_h = _parse_bb(bb)
    # Graphviz may set bb_y0 != 0 for padded graphs; total canvas height
    canvas_h = total_h - bb_y0  # usually bb_y0 == 0

    # Index all objects by their name
    obj_by_name: dict[str, dict] = {}
    for obj in gv.get("objects", []):
        obj_by_name[obj["name"]] = obj

    # Resolve node positions (Graphviz centre, flipped y).
    # Graphviz strips surrounding quotes from IDs in JSON output, so look up
    # using the raw (unquoted) node_id string.
    def _gv_node(node_id: str, w: float, h: float) -> _GvNode | None:
        obj = obj_by_name.get(node_id)
        if obj is None or "pos" not in obj:
            return None
        cx, cy_gv = _parse_pos(obj["pos"])
        cy = canvas_h - cy_gv  # flip to top-left origin
        return _GvNode(gv_id=node_id, cx=cx, cy=cy, width=w, height=h)

    # Resolve cluster bounding boxes.
    # Cluster names in JSON are the raw string after unquoting, i.e. "cluster_<id>".
    def _gv_boundary(boundary_id: str) -> _GvBoundary | None:
        obj = obj_by_name.get(f"cluster_{boundary_id}")
        if obj is None or "bb" not in obj:
            return None
        x0, y0_gv, x1, y1_gv = _parse_bb(obj["bb"])
        # In Graphviz bb: (x0,y0) is lower-left, (x1,y1) is upper-right
        top_y = canvas_h - y1_gv
        return _GvBoundary(gv_id=f"cluster_{boundary_id}", x=x0, y=top_y, width=x1 - x0, height=y1_gv - y0_gv)

    # Recompute the same uniform sizes used in _build_dot so node layouts match.
    inner_nodes = _collect_inner_nodes(diagram.root)
    inner_w, inner_h = _effective_inner_size(inner_nodes, cfg) if inner_nodes else (cfg.node_width, cfg.node_height)
    peri_w, peri_h = _effective_peripheral_size(diagram.peripheral_nodes, cfg)

    node_layouts: dict[str, NodeLayout] = {}
    boundary_layouts: dict[str, BoundaryLayout] = {}
    port_anchors: dict[str, PortAnchor] = {}

    # Walk the boundary tree and collect layouts
    def _collect_boundary(boundary: VizBoundary, is_root: bool) -> None:
        gb = _gv_boundary(boundary.id)
        if gb is not None:
            bl = BoundaryLayout(boundary_id=boundary.id, x=gb.x, y=gb.y, width=gb.width, height=gb.height)
        else:
            # Fallback: rough estimate
            bl = BoundaryLayout(boundary_id=boundary.id, x=0.0, y=0.0, width=total_w, height=canvas_h)
        boundary_layouts[boundary.id] = bl
        _add_boundary_anchors(boundary, bl, port_anchors)

        for child in boundary.children:
            if isinstance(child, VizNode):
                gn = _gv_node(child.id, inner_w, inner_h)
                if gn is not None:
                    nl = NodeLayout(
                        node_id=child.id,
                        x=gn.cx - gn.width / 2.0,
                        y=gn.cy - gn.height / 2.0,
                        width=gn.width,
                        height=gn.height,
                    )
                else:
                    nl = NodeLayout(
                        node_id=child.id, x=bl.x + 10, y=bl.y + 10, width=cfg.node_width, height=cfg.node_height
                    )
                node_layouts[child.id] = nl
                _add_node_anchors(child, nl, port_anchors)
            else:
                _collect_boundary(child, is_root=False)

    _collect_boundary(diagram.root, is_root=True)

    # Peripheral nodes
    for node in diagram.peripheral_nodes:
        gn = _gv_node(node.id, peri_w, peri_h)
        if gn is not None:
            nl = NodeLayout(
                node_id=node.id,
                x=gn.cx - gn.width / 2.0,
                y=gn.cy - gn.height / 2.0,
                width=gn.width,
                height=gn.height,
            )
        else:
            nl = NodeLayout(node_id=node.id, x=0.0, y=0.0, width=peri_w, height=peri_h)
        node_layouts[node.id] = nl
        _add_node_anchors(node, nl, port_anchors)

    # Edge routing: use Graphviz's own routes where available, fall back to
    # the obstacle-aware Z-router for edges Graphviz did not route (e.g.
    # same-owner self-connections that were omitted from the DOT source).
    gv_edges_by_id: dict[str, dict] = {e["id"]: e for e in gv.get("edges", []) if "id" in e}
    obstacles = [(nl.x, nl.y, nl.width, nl.height) for nl in node_layouts.values()]
    edge_routes: dict[str, EdgeRoute] = {}
    for edge in diagram.edges:
        gv_e = gv_edges_by_id.get(edge.id)
        if gv_e is not None:
            wps = _gv_edge_waypoints(gv_e.get("_draw_", []), gv_e.get("pos", ""), canvas_h)
            if wps is not None:
                edge_routes[edge.id] = EdgeRoute(edge_id=edge.id, waypoints=wps)
                continue
        # Fallback: Z-router for edges without a Graphviz route.
        src = port_anchors.get(edge.source_port_id)
        tgt = port_anchors.get(edge.target_port_id)
        if src and tgt:
            wps = _route_avoiding_obstacles(src.x, src.y, tgt.x, tgt.y, obstacles, canvas_h, margin=cfg.edge_margin)
            edge_routes[edge.id] = EdgeRoute(edge_id=edge.id, waypoints=wps)

    return LayoutPlan(
        diagram_id=diagram.id,
        total_width=total_w,
        total_height=canvas_h,
        nodes=node_layouts,
        boundaries=boundary_layouts,
        port_anchors=port_anchors,
        edge_routes=edge_routes,
    )
