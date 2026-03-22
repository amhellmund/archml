# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Diagrams-package backend for ArchML architecture views.

Renders a :class:`~archml.views.topology.VizDiagram` topology using the
`diagrams <https://diagrams.mingrammer.com>`_ Python package.  Layout is
delegated entirely to Graphviz (via the ``diagrams`` library); the
:class:`~archml.views.placement.LayoutPlan` argument is accepted for API
consistency but is not used.

Node-kind mapping
-----------------

- ``component`` / ``external_component`` — :class:`diagrams.generic.compute.Rack`
- ``system`` / ``external_system`` — :class:`diagrams.generic.place.Datacenter`
- ``user`` / ``external_user`` — :class:`diagrams.onprem.client.Users`
- ``channel`` — :class:`diagrams.generic.network.Switch`
- ``interface`` / ``terminal`` / unknown — :class:`diagrams.generic.blank.Blank`

Expanded entities (those containing child nodes) are rendered as labelled
Graphviz sub-graph clusters via :class:`diagrams.Cluster`.

Output format is inferred from the output file-name extension
(``".svg"``, ``".pdf"``; ``".png"`` if your Graphviz build supports it).
Unrecognised extensions default to SVG with the extension replaced by
``".svg"``.  The ``diagrams`` library appends the format extension itself,
so the written file always matches *output_path* for known extensions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from archml.views.topology import NodeKind, VizBoundary, VizDiagram, VizNode

# ###############
# Public Interface
# ###############


def render_diagrams_pkg(
    diagram: VizDiagram,
    output_path: Path,
    *,
    direction: str = "LR",
) -> None:
    """Render *diagram* to an image file using the ``diagrams`` package.

    Both layout and rendering are delegated entirely to Graphviz via the
    ``diagrams`` library.  No separate layout step is required.

    The output directory is created automatically if it does not exist.

    Args:
        diagram: Topology to render, as produced by
            :func:`~archml.views.topology.build_viz_diagram`.
        output_path: Destination file path.  The extension determines the
            output format (``".svg"``, ``".pdf"``, ``".png"``); any
            unrecognised extension defaults to SVG and is replaced by
            ``".svg"``.
        direction: Graphviz ``rankdir`` — ``"LR"`` (left-to-right, default)
            or ``"TB"`` (top-to-bottom).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _render(diagram, output_path, direction=direction)


# ################
# Implementation
# ################

_FORMAT_MAP: dict[str, str] = {
    ".svg": "svg",
    ".pdf": "pdf",
    ".png": "png",
    ".jpg": "jpg",
    ".jpeg": "jpg",
}


def _node_class(kind: NodeKind | None) -> Any:
    """Return the ``diagrams`` node class appropriate for *kind*."""
    if kind in ("user", "external_user"):
        from diagrams.onprem.client import Users

        return Users
    if kind in ("system", "external_system"):
        from diagrams.generic.place import Datacenter

        return Datacenter
    if kind in ("component", "external_component"):
        from diagrams.generic.compute import Rack

        return Rack
    if kind == "channel":
        from diagrams.generic.network import Switch

        return Switch
    # interface, terminal, unknown
    from diagrams.generic.blank import Blank

    return Blank


def _collect_ports(boundary: VizBoundary, port_map: dict[str, str]) -> None:
    """Populate *port_map* with ``port_id → owner_id`` entries for *boundary* and descendants."""
    for port in boundary.ports:
        port_map[port.id] = boundary.id
    for child in boundary.children:
        if isinstance(child, VizNode):
            for port in child.ports:
                port_map[port.id] = child.id
        elif isinstance(child, VizBoundary):
            _collect_ports(child, port_map)


def _build_boundary_contents(boundary: VizBoundary, node_map: dict[str, Any]) -> None:
    """Create diagrams nodes and nested clusters for all children of *boundary*.

    Must be called inside an active :class:`diagrams.Diagram` or
    :class:`diagrams.Cluster` context.

    For each :class:`~archml.views.topology.VizBoundary` child a
    :class:`diagrams.Cluster` is opened and its contents rendered recursively.
    When the child boundary has ports (meaning edges may reference it directly)
    a proxy :class:`~diagrams.generic.blank.Blank` node is also created inside
    the cluster so that edge connections have a target.
    """
    from diagrams import Cluster

    for child in boundary.children:
        if isinstance(child, VizNode):
            cls = _node_class(child.kind)
            node_map[child.id] = cls(child.label)
        elif isinstance(child, VizBoundary):
            with Cluster(child.title or child.label):
                if child.ports:
                    from diagrams.generic.blank import Blank

                    node_map[child.id] = Blank(child.label)
                _build_boundary_contents(child, node_map)


def _render(diagram: VizDiagram, output_path: Path, *, direction: str) -> None:
    """Build and save the diagram using the ``diagrams`` library."""
    from diagrams import Cluster, Diagram, Edge

    suffix = output_path.suffix.lower()
    outformat = _FORMAT_MAP.get(suffix, "svg")
    # diagrams appends the outformat as file extension; strip the suffix so
    # the resulting file path matches output_path exactly.  For unrecognised
    # extensions this means the final file will have the extension replaced by
    # the default format (e.g. "output.diag" → "output.svg").
    filename = str(output_path.with_suffix(""))

    graph_attr: dict[str, str] = {
        "pad": "0.5",
        "fontname": "helvetica",
    }

    node_map: dict[str, Any] = {}
    port_map: dict[str, str] = {}

    with Diagram(
        diagram.title,
        filename=filename,
        outformat=outformat,
        show=False,
        graph_attr=graph_attr,
        direction=direction,
    ):
        # Build port → owner-node-id mapping for the entire topology.
        _collect_ports(diagram.root, port_map)
        for pnode in diagram.peripheral_nodes:
            for port in pnode.ports:
                port_map[port.id] = pnode.id

        # Peripheral nodes (terminals and externals) live outside the root boundary.
        for pnode in diagram.peripheral_nodes:
            cls = _node_class(pnode.kind)
            node_map[pnode.id] = cls(pnode.label)

        # Root boundary: wrap in a Cluster unless it is the synthetic "all" root.
        if diagram.root.id == "all":
            _build_boundary_contents(diagram.root, node_map)
        else:
            with Cluster(diagram.root.title or diagram.root.label):
                if diagram.root.ports:
                    from diagrams.generic.blank import Blank

                    node_map[diagram.root.id] = Blank(diagram.root.label)
                _build_boundary_contents(diagram.root, node_map)

        # Draw directed edges between nodes.
        for edge in diagram.edges:
            src_id = port_map.get(edge.source_port_id)
            tgt_id = port_map.get(edge.target_port_id)
            if src_id is None or tgt_id is None:
                continue
            src = node_map.get(src_id)
            tgt = node_map.get(tgt_id)
            if src is None or tgt is None:
                continue
            src >> Edge(label=edge.label) >> tgt
