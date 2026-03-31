// Copyright 2026 ArchML Contributors
// SPDX-License-Identifier: Apache-2.0

// SVG renderer: produces interactive SVG markup from a VizDiagram + LayoutPlan.
// Uses CSS classes (defined in archml-diagram.css) instead of inline attributes
// so that visual style is defined once and shared with the Python SVG renderer.

import type {
  BoundaryKind,
  BoundaryLayout,
  LayoutPlan,
  NodeKind,
  NodeLayout,
  VizBoundary,
  VizDiagram,
  VizNode,
} from "./types";
import { isBoundary } from "./types";
import { collectNestedBoundaries } from "./topology";

// ─── Constants matching Python diagram.py (kept in sync) ─────────────────────

const FONT_FAMILY = "system-ui, -apple-system, sans-serif";
const FONT_SIZE = 15;
const CORNER_RADIUS = 7;
const BOUNDARY_LABEL_OFFSET = 21.0;
const LABEL_PADDING = 6.0;
const ARROW_LEN = 9.0;
const ARROW_HALF_W = 4.0;

// ─── Public API ───────────────────────────────────────────────────────────────

/** Render a VizDiagram to an interactive SVG string. */
export function renderToSvgString(diagram: VizDiagram, plan: LayoutPlan, scale = 1.0): string {
  const tw = plan.total_width * scale;
  const th = plan.total_height * scale;

  // Build entity info map for interactive attributes
  const entityInfo = collectEntityInfo(diagram);

  const defs: string[] = [];
  const elements: string[] = [];

  // Background
  elements.push(
    `<rect x="0" y="0" width="${f(plan.total_width, scale)}" height="${f(plan.total_height, scale)}" class="archml-bg"/>`,
  );

  // Root boundary
  if (diagram.root.id !== "all") {
    const rootBl = plan.boundaries[diagram.root.id];
    if (rootBl) {
      elements.push(wrapEntity(diagram.root.id, diagram.root.kind, entityInfo,
        renderBoundary(diagram.root.label, rootBl, scale, diagram.root.kind)));
    }
  }

  // Nested boundaries (BFS, outermost first)
  for (const bnd of collectNestedBoundaries(diagram.root)) {
    const bl = plan.boundaries[bnd.id];
    if (bl) {
      elements.push(wrapEntity(bnd.id, bnd.kind, entityInfo,
        renderBoundary(bnd.label, bl, scale, bnd.kind)));
    }
  }

  // Collect node metadata
  const nodeMeta = new Map<string, [string, string | null, NodeKind | null]>();
  collectNodeMeta(diagram.root, nodeMeta);
  for (const node of diagram.peripheral_nodes) {
    nodeMeta.set(node.id, [node.label, node.title, node.kind]);
  }

  // Nodes
  for (const [nodeId, nl] of Object.entries(plan.nodes)) {
    const [label, title, kind] = nodeMeta.get(nodeId) ?? [nodeId, null, null];
    const clipId = makeClipId(nodeId);
    defs.push(
      `<clipPath id="${clipId}"><rect x="${f(nl.x + LABEL_PADDING, scale)}" y="${f(nl.y, scale)}" width="${f(nl.width - 2 * LABEL_PADDING, scale)}" height="${f(nl.height, scale)}"/></clipPath>`,
    );
    elements.push(wrapEntity(nodeId, kind ?? "", entityInfo,
      renderNode(label, title, nl, kind, scale, clipId)));
  }

  // Edges
  for (const edge of diagram.edges) {
    const route = plan.edge_routes[edge.id];
    if (route) elements.push(renderEdge(route.waypoints, scale));
  }

  const svgAttrs = [
    `xmlns="http://www.w3.org/2000/svg"`,
    `viewBox="0 0 ${tw.toFixed(2)} ${th.toFixed(2)}"`,
    `width="${tw.toFixed(2)}"`,
    `height="${th.toFixed(2)}"`,
    `class="archml-svg"`,
  ].join(" ");

  return `<svg ${svgAttrs}><defs>${defs.join("")}</defs>${elements.join("")}</svg>`;
}

// ─── Internal ─────────────────────────────────────────────────────────────────

function f(value: number, scale: number): string {
  return (value * scale).toFixed(2);
}

function makeClipId(nodeId: string): string {
  const safe = nodeId.replace(/[.:/@]/g, "-");
  return `clip-${safe}`;
}

function nodeClass(kind: NodeKind | null): string {
  if (!kind) return "archml-node archml-node--unknown";
  if (kind === "component") return "archml-node archml-node--component";
  if (kind === "system") return "archml-node archml-node--system";
  if (kind === "user") return "archml-node archml-node--user";
  if (kind === "channel" || kind === "interface" || kind === "terminal")
    return "archml-node archml-node--channel";
  if (kind === "external_component" || kind === "external_system" || kind === "external_user")
    return "archml-node archml-node--external";
  return "archml-node archml-node--unknown";
}

function boundaryClass(kind: BoundaryKind | null): string {
  if (kind === "component") return "archml-boundary archml-boundary--component";
  return "archml-boundary archml-boundary--system";
}

function wrapEntity(
  id: string,
  kind: string,
  entityInfo: Map<string, [string, string, string | null]>,
  inner: string,
): string {
  const info = entityInfo.get(id);
  if (!info) return inner;
  const [ep, ek, ch] = info;
  if (!ep) return inner;
  let attrs = `class="archml-entity" data-entity-path="${escAttr(ep)}" data-entity-kind="${escAttr(ek)}" style="cursor:pointer"`;
  if (ch) attrs += ` data-channel="${escAttr(ch)}"`;
  return `<g ${attrs}>${inner}</g>`;
}

function escAttr(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderBoundary(
  label: string,
  bl: BoundaryLayout,
  scale: number,
  kind: BoundaryKind | null,
): string {
  const cls = boundaryClass(kind);
  const r = CORNER_RADIUS;
  const rect = `<rect x="${f(bl.x, scale)}" y="${f(bl.y, scale)}" width="${f(bl.width, scale)}" height="${f(bl.height, scale)}" rx="${r}" ry="${r}" class="${cls}"/>`;
  const textY = f(bl.y + BOUNDARY_LABEL_OFFSET, scale);
  const textX = f(bl.x + bl.width / 2, scale);
  const fontSize = Math.round(FONT_SIZE * scale * 1.1);
  const title = `<text x="${textX}" y="${textY}" text-anchor="middle" dominant-baseline="middle" font-family="${FONT_FAMILY}" font-size="${fontSize}" font-weight="bold" class="archml-text archml-text--boundary">${escText(label)}</text>`;
  return rect + title;
}

function renderNode(
  label: string,
  title: string | null,
  nl: NodeLayout,
  kind: NodeKind | null,
  scale: number,
  clipId: string,
): string {
  const cls = nodeClass(kind);
  const r = CORNER_RADIUS;

  const rect = `<rect x="${f(nl.x, scale)}" y="${f(nl.y, scale)}" width="${f(nl.width, scale)}" height="${f(nl.height, scale)}" rx="${r}" ry="${r}" class="${cls}"/>`;

  const cx = f(nl.x + nl.width / 2, scale);
  const cyMid = nl.y + nl.height / 2;

  let textParts: string;
  if (kind === "channel" || kind === "terminal" || kind === "interface") {
    // Single-line: interface name bold and centred.
    // For channel nodes the interface name is in title (falls back to label).
    const ifaceName = kind === "channel" ? (title ?? "") : label;
    textParts = `<text x="${cx}" y="${f(cyMid, scale)}" text-anchor="middle" dominant-baseline="middle" font-family="${FONT_FAMILY}" font-size="${Math.round(FONT_SIZE * scale)}" font-weight="bold" class="archml-text" clip-path="url(#${clipId})">${escText(ifaceName)}</text>`;
  } else {
    const isBold =
      kind === "component" || kind === "system" || kind === "interface" || kind === "terminal";
    const fontWeight = isBold ? " font-weight=\"bold\"" : "";
    textParts = `<text x="${cx}" y="${f(cyMid, scale)}" text-anchor="middle" dominant-baseline="middle" font-family="${FONT_FAMILY}" font-size="${Math.round(FONT_SIZE * scale)}"${fontWeight} class="archml-text" clip-path="url(#${clipId})">${escText(label)}</text>`;
  }

  return rect + textParts;
}

function renderEdge(waypoints: [number, number][], scale: number): string {
  if (waypoints.length < 2) return "";

  const [x1, y1] = waypoints[waypoints.length - 2];
  const [x2, y2] = waypoints[waypoints.length - 1];
  const dx = x2 - x1;
  const dy = y2 - y1;
  const length = Math.hypot(dx, dy);
  if (length < 1e-9) return "";

  const ndx = dx / length;
  const ndy = dy / length;
  const arrowLen = Math.min(ARROW_LEN, length * 0.45);
  const baseX = x2 - arrowLen * ndx;
  const baseY = y2 - arrowLen * ndy;

  const bodyWps = [...waypoints.slice(0, -1), [baseX, baseY] as [number, number]];
  const pointsStr = bodyWps.map(([x, y]) => `${(x * scale).toFixed(2)},${(y * scale).toFixed(2)}`).join(" ");
  const polyline = `<polyline points="${pointsStr}" class="archml-edge"/>`;

  const lx = baseX - ARROW_HALF_W * ndy;
  const ly = baseY + ARROW_HALF_W * ndx;
  const rx = baseX + ARROW_HALF_W * ndy;
  const ry = baseY - ARROW_HALF_W * ndx;
  const arrowPts = [[x2, y2], [lx, ly], [rx, ry]]
    .map(([x, y]) => `${(x * scale).toFixed(2)},${(y * scale).toFixed(2)}`)
    .join(" ");
  const arrow = `<polygon points="${arrowPts}" class="archml-arrowhead"/>`;

  return polyline + arrow;
}

function escText(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function collectEntityInfo(
  diagram: VizDiagram,
): Map<string, [string, string, string | null]> {
  const result = new Map<string, [string, string, string | null]>();
  walkBoundaryInfo(diagram.root, result);
  for (const node of diagram.peripheral_nodes) {
    if (node.entity_path) {
      result.set(node.id, [node.entity_path, node.kind, null]);
    } else if ((node.kind === "terminal" || node.kind === "interface") && node.label) {
      // terminal/interface peripheral nodes are clickable — show type tree in sidebar
      result.set(node.id, [node.label, node.kind, node.title]);
    }
    // channel peripheral nodes are not navigable
  }
  return result;
}

function walkBoundaryInfo(
  boundary: VizBoundary,
  result: Map<string, [string, string, string | null]>,
): void {
  if (boundary.entity_path) result.set(boundary.id, [boundary.entity_path, boundary.kind, null]);
  for (const child of boundary.children) {
    if (isBoundary(child)) {
      walkBoundaryInfo(child, result);
    } else {
      if (child.entity_path) {
        result.set(child.id, [child.entity_path, child.kind, null]);
      } else if (child.kind === "channel" && child.label) {
        // interface name is in title (falls back to channel name), channel name is label
        result.set(child.id, [child.title ?? child.label, child.kind, child.label]);
      } else if ((child.kind === "terminal" || child.kind === "interface") && child.label) {
        result.set(child.id, [child.label, child.kind, child.title]);
      }
    }
  }
}

function collectNodeMeta(
  boundary: VizBoundary,
  result: Map<string, [string, string | null, NodeKind | null]>,
): void {
  for (const child of boundary.children) {
    if (isBoundary(child)) {
      collectNodeMeta(child, result);
    } else {
      result.set(child.id, [child.label, child.title, child.kind]);
    }
  }
}
