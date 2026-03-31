// Copyright 2026 ArchML Contributors
// SPDX-License-Identifier: Apache-2.0

// DOT source generator: faithful port of Python views/layout.py _build_dot().
// Produces a Graphviz DOT string from a VizDiagram for layout computation.

import type { LayoutConfig, VizBoundary, VizDiagram, VizNode } from "./types";
import { isBoundary } from "./types";
import {
  collectBoundaryIds,
  collectInnerNodes,
  collectNodeParents,
  collectPorts,
} from "./topology";
import { effectiveInnerSize, effectivePeripheralSize } from "./placement";

export const DOT_SCALE = 72.0; // 1 layout unit = 1 pt = 1/72 inch

// ─── Public API ───────────────────────────────────────────────────────────────

export function buildDot(diagram: VizDiagram, cfg: LayoutConfig): string {
  const nsIn = cfg.node_gap / DOT_SCALE;
  const rsIn = cfg.layer_gap / DOT_SCALE;
  const pgIn = cfg.peripheral_gap / DOT_SCALE;

  const innerNodes = collectInnerNodes(diagram.root);
  const [innerW, innerH] =
    innerNodes.length > 0
      ? effectiveInnerSize(innerNodes, cfg)
      : [cfg.node_width, cfg.node_height];
  const [periW, periH] = effectivePeripheralSize(diagram.peripheral_nodes, cfg);
  const innerWIn = innerW / DOT_SCALE;
  const innerHIn = innerH / DOT_SCALE;
  const periWIn = periW / DOT_SCALE;
  const periHIn = periH / DOT_SCALE;

  const portToOwner = collectPorts(diagram.root);
  const nodeParent = collectNodeParents(diagram.root);
  const boundaryIds = collectBoundaryIds(diagram.root);

  for (const node of diagram.peripheral_nodes) {
    for (const port of node.ports) portToOwner.set(port.id, node.id);
    nodeParent.set(node.id, "__peripheral__");
  }

  // Determine which boundaries need phantom nodes (used as edge endpoints)
  const phantomBoundaries = new Set<string>();
  for (const edge of diagram.edges) {
    const srcOwner = portToOwner.get(edge.source_port_id);
    const tgtOwner = portToOwner.get(edge.target_port_id);
    if (srcOwner && boundaryIds.has(srcOwner)) phantomBoundaries.add(srcOwner);
    if (tgtOwner && boundaryIds.has(tgtOwner)) phantomBoundaries.add(tgtOwner);
  }

  const lines: string[] = [];
  lines.push("digraph G {");
  lines.push("  rankdir=LR;");
  lines.push("  compound=true;");
  lines.push(`  graph [nodesep="${nsIn.toFixed(4)}",ranksep="${rsIn.toFixed(4)}",pad="${pgIn.toFixed(4)}"];`);
  lines.push('  node [shape=box,fixedsize=true,label=""];');

  writeCluster(diagram.root, cfg, innerWIn, innerHIn, lines, "  ", phantomBoundaries);

  for (const node of diagram.peripheral_nodes) {
    const nid = dotId(node.id);
    lines.push(`  ${nid} [width="${periWIn.toFixed(4)}",height="${periHIn.toFixed(4)}",fixedsize=true,shape=box,label=""];`);
  }

  // Add phantom nodes to nodeParent for minlen computation
  for (const bid of phantomBoundaries) {
    nodeParent.set(phantomId(bid), bid);
  }

  const peripheralIds = new Set(diagram.peripheral_nodes.map((n) => n.id));

  for (const edge of diagram.edges) {
    const srcOwner = portToOwner.get(edge.source_port_id);
    const tgtOwner = portToOwner.get(edge.target_port_id);
    if (!srcOwner || !tgtOwner || srcOwner === tgtOwner) continue;

    let sid: string;
    let ltail = "";
    let srcForMinlen: string;
    if (boundaryIds.has(srcOwner)) {
      sid = dotId(phantomId(srcOwner));
      ltail = `,ltail=${dotId(`cluster_${srcOwner}`)}`;
      srcForMinlen = phantomId(srcOwner);
    } else {
      sid = dotId(srcOwner);
      srcForMinlen = srcOwner;
    }

    let tid: string;
    let lhead = "";
    let tgtForMinlen: string;
    if (boundaryIds.has(tgtOwner)) {
      tid = dotId(phantomId(tgtOwner));
      lhead = `,lhead=${dotId(`cluster_${tgtOwner}`)}`;
      tgtForMinlen = phantomId(tgtOwner);
    } else {
      tid = dotId(tgtOwner);
      tgtForMinlen = tgtOwner;
    }

    const eid = dotId(edge.id);
    let minlen: number;
    if (peripheralIds.has(srcForMinlen) || peripheralIds.has(tgtForMinlen)) {
      minlen = 3;
    } else if (nodeParent.get(srcForMinlen) !== nodeParent.get(tgtForMinlen)) {
      minlen = 2;
    } else {
      minlen = 1;
    }
    lines.push(`  ${sid} -> ${tid} [id=${eid},minlen=${minlen}${ltail}${lhead}];`);
  }

  lines.push("}");
  return lines.join("\n");
}

// ─── Internal helpers ─────────────────────────────────────────────────────────

function dotId(raw: string): string {
  const escaped = raw.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  return `"${escaped}"`;
}

const PHANTOM_PREFIX = "__ph__";

function phantomId(boundaryId: string): string {
  return `${PHANTOM_PREFIX}${boundaryId}`;
}

function writeCluster(
  boundary: VizBoundary,
  cfg: LayoutConfig,
  nodeWIn: number,
  nodeHIn: number,
  lines: string[],
  indent: string,
  phantomBoundaries: Set<string>,
): void {
  const clusterName = dotId(`cluster_${boundary.id}`);
  const padPts = cfg.boundary_padding;
  const titleFontPts = cfg.font_size * cfg.boundary_title_font_ratio;
  const label = dotId(boundary.title ?? boundary.label);

  lines.push(`${indent}subgraph ${clusterName} {`);
  lines.push(
    `${indent}  graph [label=${label},labelloc="t",fontsize="${titleFontPts.toFixed(1)}",margin="${padPts.toFixed(2)}"];`,
  );

  if (phantomBoundaries.has(boundary.id)) {
    const pid = dotId(phantomId(boundary.id));
    const hasChildren = boundary.children.length > 0;
    if (hasChildren) {
      lines.push(`${indent}  ${pid} [style=invis,width=0,height=0,fixedsize=true];`);
    } else {
      lines.push(
        `${indent}  ${pid} [style=invis,width="${nodeWIn.toFixed(4)}",height="${nodeHIn.toFixed(4)}",fixedsize=true];`,
      );
    }
  } else if (boundary.children.length === 0) {
    // Empty cluster with no phantom: Graphviz won't compute a bounding box
    // without at least one node. Add an invisible placeholder so the cluster
    // gets a proper size (e.g. an empty system like `system Standalone {}`).
    const pid = dotId(`__empty__${boundary.id}`);
    lines.push(
      `${indent}  ${pid} [style=invis,width="${nodeWIn.toFixed(4)}",height="${nodeHIn.toFixed(4)}",fixedsize=true];`,
    );
  }

  for (const child of boundary.children) {
    if (isBoundary(child)) {
      writeCluster(child, cfg, nodeWIn, nodeHIn, lines, indent + "  ", phantomBoundaries);
    } else {
      const nid = dotId(child.id);
      lines.push(
        `${indent}  ${nid} [width="${nodeWIn.toFixed(4)}",height="${nodeHIn.toFixed(4)}",fixedsize=true,shape=box,label=""];`,
      );
    }
  }
  lines.push(`${indent}}`);
}
