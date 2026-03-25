// Copyright 2026 ArchML Contributors
// SPDX-License-Identifier: Apache-2.0

// Layout computation: calls @viz-js/viz (WASM Graphviz) and converts JSON output
// into a LayoutPlan. Faithful port of Python views/layout.py _parse_to_plan().

import type {
  BoundaryLayout,
  EdgeRoute,
  LayoutConfig,
  LayoutPlan,
  NodeLayout,
  PortAnchor,
  VizBoundary,
  VizDiagram,
  VizNode,
} from "./types";
import { isBoundary, defaultLayoutConfig } from "./types";
import { buildDot, DOT_SCALE } from "./dot";
import {
  addBoundaryAnchors,
  addNodeAnchors,
  effectiveInnerSize,
  effectivePeripheralSize,
  routeAvoidingObstacles,
} from "./placement";
import { collectInnerNodes } from "./topology";

// ─── Public API ───────────────────────────────────────────────────────────────

// Singleton viz instance cache
let _vizInstance: import("@viz-js/viz").Viz | null = null;

async function getViz(): Promise<import("@viz-js/viz").Viz> {
  if (!_vizInstance) {
    const { instance } = await import("@viz-js/viz");
    _vizInstance = await instance();
  }
  return _vizInstance;
}

export async function computeLayout(
  diagram: VizDiagram,
  cfg: LayoutConfig = defaultLayoutConfig(),
): Promise<LayoutPlan> {
  const dotSrc = buildDot(diagram, cfg);
  const viz = await getViz();
  const gvJson = viz.renderJSON(dotSrc);
  return parseToLayoutPlan(diagram, gvJson, cfg);
}

// ─── Internal helpers ─────────────────────────────────────────────────────────

interface GvNode {
  gvId: string;
  cx: number;
  cy: number;
  width: number;
  height: number;
}

interface GvBoundary {
  gvId: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

function parseBb(bb: string): [number, number, number, number] {
  const parts = bb.split(",").map(Number);
  return [parts[0], parts[1], parts[2], parts[3]];
}

function parsePos(pos: string): [number, number] {
  const [x, y] = pos.split(",").map(Number);
  return [x, y];
}

function sampleCubicBezier(
  p0: number[],
  p1: number[],
  p2: number[],
  p3: number[],
  n = 8,
): [number, number][] {
  const pts: [number, number][] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const mt = 1 - t;
    const x = mt ** 3 * p0[0] + 3 * mt ** 2 * t * p1[0] + 3 * mt * t ** 2 * p2[0] + t ** 3 * p3[0];
    const y = mt ** 3 * p0[1] + 3 * mt ** 2 * t * p1[1] + 3 * mt * t ** 2 * p2[1] + t ** 3 * p3[1];
    pts.push([x, y]);
  }
  return pts;
}

function gvEdgeWaypoints(
  drawOps: Record<string, unknown>[],
  posStr: string,
  canvasH: number,
): [number, number][] | null {
  let endpoint: [number, number] | null = null;
  if (posStr.startsWith("e,")) {
    const raw = posStr.split(" ")[0].slice(2);
    const [ex, ey] = raw.split(",").map(Number);
    endpoint = [ex, canvasH - ey];
  }

  let ctrl: number[][] = [];
  for (const op of drawOps) {
    if (op["op"] === "b") {
      ctrl = op["points"] as number[][];
      break;
    }
  }
  if (ctrl.length === 0) return null;

  const nSegs = Math.floor((ctrl.length - 1) / 3);
  let waypoints: [number, number][] = [];
  for (let seg = 0; seg < nSegs; seg++) {
    const i = seg * 3;
    let pts = sampleCubicBezier(ctrl[i], ctrl[i + 1], ctrl[i + 2], ctrl[i + 3]);
    if (seg > 0) pts = pts.slice(1);
    waypoints = waypoints.concat(pts);
  }

  waypoints = waypoints.map(([x, y]) => [x, canvasH - y]);
  if (endpoint) waypoints.push(endpoint);
  return waypoints.length > 0 ? waypoints : null;
}

function parseToLayoutPlan(
  diagram: VizDiagram,
  gv: Record<string, unknown>,
  cfg: LayoutConfig,
): LayoutPlan {
  const bbStr = (gv["bb"] as string) ?? "";
  if (!bbStr) throw new Error("Graphviz output missing 'bb' attribute.");

  const [, bbY0, totalW, totalH] = parseBb(bbStr);
  const canvasH = totalH - bbY0;

  // Index objects by name (Graphviz strips quotes)
  const objByName = new Map<string, Record<string, unknown>>();
  for (const obj of (gv["objects"] as Record<string, unknown>[]) ?? []) {
    objByName.set(obj["name"] as string, obj);
  }

  function gvNode(nodeId: string, w: number, h: number): GvNode | null {
    const obj = objByName.get(nodeId);
    if (!obj || !obj["pos"]) return null;
    const [cx, cyGv] = parsePos(obj["pos"] as string);
    const cy = canvasH - cyGv;
    return { gvId: nodeId, cx, cy, width: w, height: h };
  }

  function gvBoundary(boundaryId: string): GvBoundary | null {
    const obj = objByName.get(`cluster_${boundaryId}`);
    if (!obj || !obj["bb"]) return null;
    const [x0, y0Gv, x1, y1Gv] = parseBb(obj["bb"] as string);
    const topY = canvasH - y1Gv;
    return { gvId: `cluster_${boundaryId}`, x: x0, y: topY, width: x1 - x0, height: y1Gv - y0Gv };
  }

  const innerNodes = collectInnerNodes(diagram.root);
  const [innerW, innerH] =
    innerNodes.length > 0
      ? effectiveInnerSize(innerNodes, cfg)
      : [cfg.node_width, cfg.node_height];
  const [periW, periH] = effectivePeripheralSize(diagram.peripheral_nodes, cfg);

  const nodeLayouts = new Map<string, NodeLayout>();
  const boundaryLayouts = new Map<string, BoundaryLayout>();
  const portAnchors = new Map<string, PortAnchor>();

  function collectBoundary(boundary: VizBoundary): void {
    const gb = gvBoundary(boundary.id);
    let bl: BoundaryLayout;
    if (gb) {
      bl = { boundary_id: boundary.id, x: gb.x, y: gb.y, width: gb.width, height: gb.height };
    } else {
      bl = { boundary_id: boundary.id, x: 0, y: 0, width: totalW, height: canvasH };
    }
    boundaryLayouts.set(boundary.id, bl);
    addBoundaryAnchors(boundary, bl, portAnchors);

    for (const child of boundary.children) {
      if (isBoundary(child)) {
        collectBoundary(child);
      } else {
        const gn = gvNode(child.id, innerW, innerH);
        let nl: NodeLayout;
        if (gn) {
          nl = {
            node_id: child.id,
            x: gn.cx - gn.width / 2,
            y: gn.cy - gn.height / 2,
            width: gn.width,
            height: gn.height,
          };
        } else {
          nl = { node_id: child.id, x: bl.x + 10, y: bl.y + 10, width: cfg.node_width, height: cfg.node_height };
        }
        nodeLayouts.set(child.id, nl);
        addNodeAnchors(child, nl, portAnchors);
      }
    }
  }

  collectBoundary(diagram.root);

  // Peripheral nodes
  for (const node of diagram.peripheral_nodes) {
    const gn = gvNode(node.id, periW, periH);
    let nl: NodeLayout;
    if (gn) {
      nl = { node_id: node.id, x: gn.cx - gn.width / 2, y: gn.cy - gn.height / 2, width: gn.width, height: gn.height };
    } else {
      nl = { node_id: node.id, x: 0, y: 0, width: periW, height: periH };
    }
    nodeLayouts.set(node.id, nl);
    addNodeAnchors(node, nl, portAnchors);
  }

  // Edge routing
  const gvEdgesById = new Map<string, Record<string, unknown>>();
  for (const e of (gv["edges"] as Record<string, unknown>[]) ?? []) {
    if (e["id"]) gvEdgesById.set(e["id"] as string, e);
  }

  const obstacles: [number, number, number, number][] = [...nodeLayouts.values()].map(
    (nl) => [nl.x, nl.y, nl.width, nl.height],
  );
  const edgeRoutes = new Map<string, EdgeRoute>();

  for (const edge of diagram.edges) {
    const gvE = gvEdgesById.get(edge.id);
    if (gvE) {
      const wps = gvEdgeWaypoints(
        (gvE["_draw_"] as Record<string, unknown>[]) ?? [],
        (gvE["pos"] as string) ?? "",
        canvasH,
      );
      if (wps) {
        edgeRoutes.set(edge.id, { edge_id: edge.id, waypoints: wps });
        continue;
      }
    }
    // Fallback: obstacle-aware Z-router
    const src = portAnchors.get(edge.source_port_id);
    const tgt = portAnchors.get(edge.target_port_id);
    if (src && tgt) {
      const wps = routeAvoidingObstacles(src.x, src.y, tgt.x, tgt.y, obstacles, canvasH, 4.0, cfg.edge_margin);
      edgeRoutes.set(edge.id, { edge_id: edge.id, waypoints: wps });
    }
  }

  // Convert Maps to Records for the LayoutPlan
  const nodes: Record<string, NodeLayout> = {};
  nodeLayouts.forEach((v, k) => (nodes[k] = v));
  const boundaries: Record<string, BoundaryLayout> = {};
  boundaryLayouts.forEach((v, k) => (boundaries[k] = v));
  const port_anchors: Record<string, PortAnchor> = {};
  portAnchors.forEach((v, k) => (port_anchors[k] = v));
  const edge_routes: Record<string, EdgeRoute> = {};
  edgeRoutes.forEach((v, k) => (edge_routes[k] = v));

  return {
    diagram_id: diagram.id,
    total_width: totalW,
    total_height: canvasH,
    nodes,
    boundaries,
    port_anchors,
    edge_routes,
  };
}
