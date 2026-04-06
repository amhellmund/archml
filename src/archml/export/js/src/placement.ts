// Copyright 2026 ArchML Contributors
// SPDX-License-Identifier: Apache-2.0

// Layout sizing helpers and port-anchor computation.
// Faithful TypeScript port of Python views/placement.py helper functions.

import type { LayoutConfig, NodeLayout, BoundaryLayout, PortAnchor, VizNode, VizBoundary } from "./types";

// ─── Text-aware sizing ────────────────────────────────────────────────────────

export function requiredTextWidth(
  text: string,
  cfg: LayoutConfig,
  bold = false,
  fontRatio = 1.0,
): number {
  const charW = cfg.approx_char_width * (bold ? cfg.bold_char_width_factor : 1.0) * fontRatio;
  return text.length * charW + cfg.text_h_padding;
}

export function minChannelNodeHeight(cfg: LayoutConfig): number {
  return cfg.font_size + cfg.channel_line_gap + cfg.font_size * cfg.channel_label_font_ratio + cfg.node_v_padding;
}

export function effectiveInnerSize(nodes: VizNode[], cfg: LayoutConfig): [number, number] {
  let w = cfg.node_width;
  let h = cfg.node_height;
  for (const node of nodes) {
    let needed: number;
    if (node.kind === "channel") {
      const iface = node.title ?? node.label;
      needed = Math.max(
        requiredTextWidth(iface, cfg, true),
        requiredTextWidth(`$${node.label}`, cfg, false, cfg.channel_label_font_ratio),
      );
      h = Math.max(h, minChannelNodeHeight(cfg));
    } else if (node.kind === "component" || node.kind === "system") {
      needed = requiredTextWidth(node.label, cfg, true);
    } else if (node.kind === "user" || node.kind === "external_user") {
      needed = requiredTextWidth(node.label, cfg);
      const iconMinH =
        cfg.user_icon_pad + cfg.user_icon_size + cfg.user_icon_pad + cfg.font_size + cfg.node_v_padding / 2;
      h = Math.max(h, iconMinH);
    } else {
      needed = requiredTextWidth(node.label, cfg);
    }
    w = Math.max(w, needed);
  }
  return [w, h];
}

export function effectivePeripheralSize(nodes: VizNode[], cfg: LayoutConfig): [number, number] {
  let w = cfg.peripheral_node_width;
  let h = cfg.peripheral_node_height;
  for (const node of nodes) {
    w = Math.max(w, requiredTextWidth(node.label, cfg));
    if (node.kind === "user" || node.kind === "external_user") {
      const iconMinH =
        cfg.user_icon_pad + cfg.user_icon_size + cfg.user_icon_pad + cfg.font_size + cfg.node_v_padding / 2;
      h = Math.max(h, iconMinH);
    }
  }
  return [w, h];
}

// ─── Port anchoring ───────────────────────────────────────────────────────────

function anchorPortsOnEdge(
  ports: { id: string }[],
  edgeX: number,
  topY: number,
  height: number,
  out: Map<string, PortAnchor>,
): void {
  const n = ports.length;
  if (n === 0) return;
  ports.forEach((port, i) => {
    const y = topY + ((i + 1) * height) / (n + 1);
    out.set(port.id, { port_id: port.id, x: edgeX, y });
  });
}

export function addNodeAnchors(
  node: VizNode,
  layout: NodeLayout,
  out: Map<string, PortAnchor>,
): void {
  const req = node.ports.filter((p) => p.direction === "requires");
  const prov = node.ports.filter((p) => p.direction === "provides");
  anchorPortsOnEdge(req, layout.x, layout.y, layout.height, out);
  anchorPortsOnEdge(prov, layout.x + layout.width, layout.y, layout.height, out);
}

export function addBoundaryAnchors(
  boundary: VizBoundary,
  layout: BoundaryLayout,
  out: Map<string, PortAnchor>,
): void {
  const req = boundary.ports.filter((p) => p.direction === "requires");
  const prov = boundary.ports.filter((p) => p.direction === "provides");
  anchorPortsOnEdge(req, layout.x, layout.y, layout.height, out);
  anchorPortsOnEdge(prov, layout.x + layout.width, layout.y, layout.height, out);
}

// ─── Obstacle-aware orthogonal routing ───────────────────────────────────────

type Rect = [number, number, number, number]; // [x, y, w, h]

function segmentHClear(y: number, x1: number, x2: number, obstacles: Rect[]): boolean {
  const lo = Math.min(x1, x2);
  const hi = Math.max(x1, x2);
  return obstacles.every(([ox, oy, ow, oh]) => !(ox < hi && ox + ow > lo && oy < y && y < oy + oh));
}

function segmentVClear(x: number, y1: number, y2: number, obstacles: Rect[]): boolean {
  const lo = Math.min(y1, y2);
  const hi = Math.max(y1, y2);
  return obstacles.every(([ox, oy, ow, oh]) => !(oy < hi && oy + oh > lo && ox < x && x < ox + ow));
}

function routeIsClear(waypoints: [number, number][], obstacles: Rect[]): boolean {
  for (let i = 0; i < waypoints.length - 1; i++) {
    const [x1, y1] = waypoints[i];
    const [x2, y2] = waypoints[i + 1];
    if (Math.abs(x1 - x2) < 0.5) {
      if (!segmentVClear(x1, y1, y2, obstacles)) return false;
    } else {
      if (!segmentHClear(y1, x1, x2, obstacles)) return false;
    }
  }
  return true;
}

function freeCorridorXs(sx: number, tx: number, obstacles: Rect[]): number[] {
  if (tx <= sx) return [];
  const blocked: [number, number][] = [];
  for (const [ox, , ow] of obstacles) {
    const lo = Math.max(ox, sx);
    const hi = Math.min(ox + ow, tx);
    if (lo < hi) blocked.push([lo, hi]);
  }
  blocked.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const [lo, hi] of blocked) {
    if (merged.length > 0 && lo <= merged[merged.length - 1][1]) {
      merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], hi);
    } else {
      merged.push([lo, hi]);
    }
  }
  const corridors: number[] = [];
  let prev = sx;
  for (const [lo, hi] of merged) {
    if (lo > prev + 0.5) corridors.push((prev + lo) / 2.0);
    prev = hi;
  }
  if (tx > prev + 0.5) corridors.push((prev + tx) / 2.0);
  return corridors;
}

function bypassLevels(
  x1: number,
  x2: number,
  obstacles: Rect[],
  totalHeight: number,
  gap: number,
): number[] {
  const loX = Math.min(x1, x2);
  const hiX = Math.max(x1, x2);
  const relevant = obstacles.filter(([ox, , ow]) => ox < hiX && ox + ow > loX);
  if (relevant.length === 0) return [];
  const top = Math.min(...relevant.map(([, oy]) => oy));
  const bottom = Math.max(...relevant.map(([, oy, , oh]) => oy + oh));
  return [top - gap, bottom + gap];
}

function inflateObstacles(obstacles: Rect[], sx: number, tx: number, margin: number): Rect[] {
  if (margin <= 0) return [...obstacles];
  return obstacles.map(([ox, oy, ow, oh]) => {
    if (Math.abs(ox + ow - sx) < 0.5 || Math.abs(ox - tx) < 0.5) {
      return [ox, oy, ow, oh];
    }
    return [ox - margin, oy - margin, ow + 2 * margin, oh + 2 * margin];
  });
}

export function routeAvoidingObstacles(
  sx: number,
  sy: number,
  tx: number,
  ty: number,
  obstacles: Rect[],
  totalHeight: number,
  gap = 4.0,
  margin = 0.0,
): [number, number][] {
  const obs = inflateObstacles(obstacles, sx, tx, margin);

  if (Math.abs(sy - ty) < 0.5) {
    const wps: [number, number][] = [[sx, sy], [tx, ty]];
    if (routeIsClear(wps, obs)) return wps;
  }

  const cxs = freeCorridorXs(sx, tx, obs);

  for (const cx of cxs) {
    const wps: [number, number][] = [[sx, sy], [cx, sy], [cx, ty], [tx, ty]];
    if (routeIsClear(wps, obs)) return wps;
  }

  const cx1 = cxs.length > 0 ? cxs[0] : (sx + tx) / 2;
  const cx2 = cxs.length > 0 ? cxs[cxs.length - 1] : (sx + tx) / 2;
  const midY = (sy + ty) / 2;
  const bypassCandidates = bypassLevels(cx1, cx2, obs, totalHeight, gap)
    .sort((a, b) => Math.abs(a - midY) - Math.abs(b - midY));

  for (const by of bypassCandidates) {
    let wps: [number, number][];
    if (cx1 !== cx2) {
      wps = [[sx, sy], [cx1, sy], [cx1, by], [cx2, by], [cx2, ty], [tx, ty]];
    } else {
      wps = [[sx, sy], [cx1, sy], [cx1, by], [tx, by], [tx, ty]];
    }
    if (routeIsClear(wps, obs)) return wps;
  }

  const midX = (sx + tx) / 2;
  if (Math.abs(sy - ty) < 0.5) {
    for (const by of bypassLevels(midX, midX, obs, totalHeight, gap)
      .sort((a, b) => Math.abs(a - midY) - Math.abs(b - midY))) {
      const wps: [number, number][] = [[sx, sy], [midX, sy], [midX, by], [tx, by], [tx, ty]];
      if (routeIsClear(wps, obs)) return wps;
    }
  }
  return [[sx, sy], [midX, sy], [midX, ty], [tx, ty]];
}
