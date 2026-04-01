// Copyright 2026 ArchML Contributors
// SPDX-License-Identifier: Apache-2.0

// TypeScript types mirroring the Python Pydantic model serialisation output
// (model_dump(mode="json")) and the viewer payload produced by export.py.

// ─── Architecture model (Pydantic JSON output) ───────────────────────────────

export interface InterfaceRefJson {
  name: string;
  version: string | null;
  port_name: string | null;
  line: number;
}

export interface ConnectDefJson {
  src_entity: string | null;
  src_port: string | null;
  channel: string | null;
  dst_entity: string | null;
  dst_port: string | null;
  variants: string[];
  line: number;
}

export interface ExposeDefJson {
  entity: string;
  port: string;
  as_name: string | null;
  line: number;
}

export interface UserDefJson {
  name: string;
  title: string | null;
  description: string | null;
  tags: string[];
  requires: InterfaceRefJson[];
  provides: InterfaceRefJson[];
  is_external: boolean;
  qualified_name: string;
  line: number;
}

export interface ComponentJson {
  name: string;
  title: string | null;
  description: string | null;
  tags: string[];
  variants: string[];
  requires: InterfaceRefJson[];
  provides: InterfaceRefJson[];
  interfaces: InterfaceDefJson[];
  components: ComponentJson[];
  connects: ConnectDefJson[];
  exposes: ExposeDefJson[];
  is_external: boolean;
  is_stub: boolean;
  qualified_name: string;
  line: number;
}

export interface SystemJson {
  name: string;
  title: string | null;
  description: string | null;
  tags: string[];
  variants: string[];
  requires: InterfaceRefJson[];
  provides: InterfaceRefJson[];
  interfaces: InterfaceDefJson[];
  components: ComponentJson[];
  systems: SystemJson[];
  users: UserDefJson[];
  connects: ConnectDefJson[];
  exposes: ExposeDefJson[];
  is_external: boolean;
  is_stub: boolean;
  qualified_name: string;
  line: number;
}

export type PrimitiveKind =
  | "String"
  | "Int"
  | "Float"
  | "Decimal"
  | "Bool"
  | "Bytes"
  | "Timestamp"
  | "Datetime";

export type TypeRefJson =
  | { kind: "primitive"; primitive: PrimitiveKind }
  | { kind: "list"; element_type: TypeRefJson }
  | { kind: "map"; key_type: TypeRefJson; value_type: TypeRefJson }
  | { kind: "optional"; inner_type: TypeRefJson }
  | { kind: "named"; name: string };

export interface FieldDefJson {
  name: string;
  type: TypeRefJson;
  description: string | null;
  schema_ref: string | null;
  line: number;
}

export interface InterfaceDefJson {
  name: string;
  version: string | null;
  fields: FieldDefJson[];
  title: string | null;
  description: string | null;
  tags: string[];
  variants: string[];
  qualified_name: string;
  line: number;
}

export interface TypeDefJson {
  name: string;
  fields: FieldDefJson[];
  title: string | null;
  description: string | null;
  tags: string[];
  line: number;
}

export interface EnumDefJson {
  name: string;
  values: string[];
  title: string | null;
  description: string | null;
  tags: string[];
  line: number;
}

export interface ArchFileJson {
  imports: unknown[];
  enums: EnumDefJson[];
  types: TypeDefJson[];
  interfaces: InterfaceDefJson[];
  components: ComponentJson[];
  systems: SystemJson[];
  users: UserDefJson[];
  connects: ConnectDefJson[];
}

// ─── Viewer payload (output of build_viewer_payload) ─────────────────────────

export interface EntityEntry {
  qualified_name: string;
  kind: "system" | "component" | "external_system" | "external_component";
  title: string | null;
  file_key: string;
}

export interface ViewerPayload {
  version: string;
  files: Record<string, ArchFileJson>;
  entities: EntityEntry[];
  widthOptimized?: boolean;
}

// ─── Topology model (mirrors Python views/topology.py dataclasses) ───────────

export type NodeKind =
  | "component"
  | "system"
  | "user"
  | "external_component"
  | "external_system"
  | "external_user"
  | "terminal"
  | "channel"
  | "interface";

export type BoundaryKind = "component" | "system";

export interface VizPort {
  id: string;
  node_id: string;
  interface_name: string;
  interface_version: string | null;
  direction: "requires" | "provides";
  description?: string | null;
}

export interface VizNode {
  id: string;
  label: string;
  title: string | null;
  kind: NodeKind;
  entity_path: string;
  description?: string | null;
  tags: string[];
  ports: VizPort[];
}

export interface VizBoundary {
  id: string;
  label: string;
  title: string | null;
  kind: BoundaryKind;
  entity_path: string;
  description?: string | null;
  tags: string[];
  ports: VizPort[];
  children: (VizNode | VizBoundary)[];
}

export interface VizEdge {
  id: string;
  source_port_id: string;
  target_port_id: string;
  label: string;
  interface_name: string;
  interface_version: string | null;
}

export interface VizDiagram {
  id: string;
  title: string;
  description: string | null;
  root: VizBoundary;
  peripheral_nodes: VizNode[];
  edges: VizEdge[];
}

// ─── Layout plan (mirrors Python views/placement.py) ─────────────────────────

export interface LayoutConfig {
  node_width: number;
  node_height: number;
  layer_gap: number;
  node_gap: number;
  peripheral_gap: number;
  boundary_padding: number;
  boundary_title_reserve: number;
  boundary_bottom_extra_padding: number;
  peripheral_node_width: number;
  peripheral_node_height: number;
  approx_char_width: number;
  bold_char_width_factor: number;
  text_h_padding: number;
  font_size: number;
  node_v_padding: number;
  channel_line_gap: number;
  channel_label_font_ratio: number;
  boundary_title_font_ratio: number;
  diagram_margin: number;
  edge_margin: number;
}

export function defaultLayoutConfig(): LayoutConfig {
  return {
    node_width: 120.0,
    node_height: 80.0,
    layer_gap: 80.0,
    node_gap: 40.0,
    peripheral_gap: 80.0,
    boundary_padding: 40.0,
    boundary_title_reserve: 35.0,
    boundary_bottom_extra_padding: 15.0,
    peripheral_node_width: 100.0,
    peripheral_node_height: 68.0,
    approx_char_width: 9.5,
    bold_char_width_factor: 1.1,
    text_h_padding: 24.0,
    font_size: 15.0,
    node_v_padding: 28.0,
    channel_line_gap: 8.0,
    channel_label_font_ratio: 0.9,
    boundary_title_font_ratio: 1.1,
    diagram_margin: 4.0,
    edge_margin: 8.0,
  };
}

export interface PortAnchor {
  port_id: string;
  x: number;
  y: number;
}

export interface NodeLayout {
  node_id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface BoundaryLayout {
  boundary_id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface EdgeRoute {
  edge_id: string;
  waypoints: [number, number][];
}

export interface LayoutPlan {
  diagram_id: string;
  total_width: number;
  total_height: number;
  nodes: Record<string, NodeLayout>;
  boundaries: Record<string, BoundaryLayout>;
  port_anchors: Record<string, PortAnchor>;
  edge_routes: Record<string, EdgeRoute>;
}

// ─── Entity type guard ────────────────────────────────────────────────────────

export function isBoundary(child: VizNode | VizBoundary): child is VizBoundary {
  return "children" in child;
}
