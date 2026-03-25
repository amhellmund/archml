// Copyright 2026 ArchML Contributors
// SPDX-License-Identifier: Apache-2.0

// Topology builder: faithful TypeScript port of Python views/topology.py.
// Converts compiled ArchFile model data into the abstract VizDiagram topology.

import type {
  ArchFileJson,
  ComponentJson,
  ConnectDefJson,
  ExposeDefJson,
  InterfaceRefJson,
  SystemJson,
  UserDefJson,
  BoundaryKind,
  NodeKind,
  VizBoundary,
  VizDiagram,
  VizEdge,
  VizNode,
  VizPort,
} from "./types";
import { isBoundary } from "./types";

// ─── Public API ───────────────────────────────────────────────────────────────

export function buildVizDiagram(
  entity: ComponentJson | SystemJson,
  depth: number | null = null,
  globalConnects: ConnectDefJson[] = [],
): VizDiagram {
  const entityPath = entity.qualified_name || entity.name;
  const rootId = makeId(entityPath);

  // Sub-entity map for connect/expose port lookups
  const allSubEntityMap = new Map<string, ComponentJson | SystemJson | UserDefJson>();
  for (const comp of entity.components) allSubEntityMap.set(comp.name, comp);
  if (isSystem(entity)) {
    for (const sys of entity.systems) allSubEntityMap.set(sys.name, sys);
    for (const user of entity.users) allSubEntityMap.set(user.name, user);
  }

  // Child nodes
  const opaquChildMap = new Map<string, VizNode>();
  const expandedBoundaryMap = new Map<string, VizBoundary>();
  const childExposeMaps = new Map<string, ExposeMap>();
  let allInnerEdges: VizEdge[] = [];

  if (depth !== 0) {
    const remaining = depth === null ? null : depth - 1;
    for (const [childName, child] of allSubEntityMap) {
      const childPath = `${entityPath}::${child.name}`;
      const shouldExpand =
        !isUser(child) &&
        shouldExpandEntity(child) &&
        (remaining === null || remaining > 0);
      if (shouldExpand && !isUser(child)) {
        const childRemaining = remaining === null ? null : remaining - 1;
        const [bnd, innerEdges, exposeMap] = buildRecursiveBoundary(
          child as ComponentJson | SystemJson,
          childPath,
          childRemaining,
        );
        expandedBoundaryMap.set(childName, bnd);
        childExposeMaps.set(childName, exposeMap);
        allInnerEdges = allInnerEdges.concat(innerEdges);
      } else {
        opaquChildMap.set(childName, makeChildNode(child, childPath));
      }
    }
  }

  // Channel nodes
  const channelNodeMap =
    depth !== 0
      ? collectChannelNodesResolve(
          entity.connects,
          rootId,
          allSubEntityMap,
          opaquChildMap,
          childExposeMaps,
        )
      : new Map<string, VizNode>();

  // Root boundary
  const rootPorts = makePorts(rootId, entity);
  const allChildren: (VizNode | VizBoundary)[] = [
    ...opaquChildMap.values(),
    ...expandedBoundaryMap.values(),
    ...channelNodeMap.values(),
  ];
  const root: VizBoundary = {
    id: rootId,
    label: entity.name,
    title: entity.title,
    kind: isSystem(entity) ? "system" : "component",
    entity_path: entityPath,
    description: entity.description,
    tags: [...entity.tags],
    ports: rootPorts,
    children: allChildren,
  };

  // Peripheral nodes (terminal interface anchors)
  const peripheralNodes: VizNode[] = [];
  const extConnects = globalConnects;
  for (const ref of entity.requires) {
    const ch = findChannelForPort(entity.name, "requires", ref.name, extConnects);
    peripheralNodes.push(makeTerminalNode(ref, "requires", "terminal", ch));
  }
  for (const ref of entity.provides) {
    const ch = findChannelForPort(entity.name, "provides", ref.name, extConnects);
    peripheralNodes.push(makeTerminalNode(ref, "provides", "terminal", ch));
  }

  // Expose-based terminal nodes
  const seenExposeTerminalIds = new Set<string>();
  for (const exp of entity.exposes) {
    const childEnt = allSubEntityMap.get(exp.entity);
    if (!childEnt) continue;
    const portRes = resolvePortRef(childEnt, exp.port);
    if (!portRes) continue;
    const [expDir, expRef] = portRes;
    const dirTag = expDir === "requires" ? "req" : "prov";
    const termId = `terminal.${dirTag}.${irefLabel(expRef)}`;
    if (!seenExposeTerminalIds.has(termId)) {
      seenExposeTerminalIds.add(termId);
      const ch = findChannelForPort(entity.name, expDir, expRef.name, extConnects);
      peripheralNodes.push(makeTerminalNode(expRef, expDir, "interface", ch));
    }
  }

  // Edges
  const edges: VizEdge[] = [];
  const seenPortPairs = new Set<string>();

  function addEdge(edge: VizEdge): void {
    const key = `${edge.source_port_id}||${edge.target_port_id}`;
    if (!seenPortPairs.has(key)) {
      seenPortPairs.add(key);
      edges.push(edge);
    }
  }

  for (const edge of allInnerEdges) addEdge(edge);

  if (depth !== 0) {
    for (const conn of entity.connects) {
      for (const edge of buildEdgesFromConnectResolve(
        conn,
        opaquChildMap,
        expandedBoundaryMap,
        allSubEntityMap,
        channelNodeMap,
        childExposeMaps,
      )) {
        addEdge(edge);
      }
    }
  }

  // Terminal boundary edges (requires)
  for (const ref of entity.requires) {
    const termId = `terminal.req.${irefLabel(ref)}`;
    const termPortId = `${termId}.port`;
    const rootPortId = portId(rootId, "requires", ref);
    const key = `${termPortId}||${rootPortId}`;
    if (!seenPortPairs.has(key)) {
      seenPortPairs.add(key);
      edges.push({
        id: `edge.${termPortId}--${rootPortId}`,
        source_port_id: termPortId,
        target_port_id: rootPortId,
        label: irefLabel(ref),
        interface_name: ref.name,
        interface_version: ref.version,
      });
    }
  }
  for (const ref of entity.provides) {
    const termId = `terminal.prov.${irefLabel(ref)}`;
    const termPortId = `${termId}.port`;
    const rootPortId = portId(rootId, "provides", ref);
    const key = `${rootPortId}||${termPortId}`;
    if (!seenPortPairs.has(key)) {
      seenPortPairs.add(key);
      edges.push({
        id: `edge.${rootPortId}--${termPortId}`,
        source_port_id: rootPortId,
        target_port_id: termPortId,
        label: irefLabel(ref),
        interface_name: ref.name,
        interface_version: ref.version,
      });
    }
  }

  // Expose-based terminal edges
  for (const exp of entity.exposes) {
    const childEnt = allSubEntityMap.get(exp.entity);
    if (!childEnt) continue;
    let connPortId: string | null = null;
    let expDir: "requires" | "provides";
    let expRef: InterfaceRefJson;

    const childNode = opaquChildMap.get(exp.entity);
    if (childNode) {
      const portRes = resolvePortRef(childEnt, exp.port);
      if (!portRes) continue;
      [expDir, expRef] = portRes;
      connPortId = findPortId(childNode, expDir, expRef);
      if (!connPortId) {
        const p = makePort(childNode.id, expDir, expRef);
        childNode.ports.push(p);
        connPortId = p.id;
      }
    } else if (expandedBoundaryMap.has(exp.entity)) {
      const bnd = expandedBoundaryMap.get(exp.entity)!;
      const inner = childExposeMaps.get(exp.entity)?.get(exp.port);
      if (inner) {
        const [leafNode, leafEntity, leafPort] = inner;
        const leafRes = findRefByPortName(leafEntity, leafPort);
        if (!leafRes) continue;
        [expDir, expRef] = leafRes;
        connPortId = findPortId(leafNode, expDir, expRef);
        if (!connPortId) {
          const p = makePort(leafNode.id, expDir, expRef);
          leafNode.ports.push(p);
          connPortId = p.id;
        }
      } else {
        const portRes = resolvePortRef(childEnt, exp.port);
        if (!portRes) continue;
        [expDir, expRef] = portRes;
        connPortId = findPortId(bnd, expDir, expRef);
        if (!connPortId) {
          const p = makePort(bnd.id, expDir, expRef);
          bnd.ports.push(p);
          connPortId = p.id;
        }
      }
    } else {
      const portRes = resolvePortRef(childEnt, exp.port);
      if (!portRes) continue;
      [expDir, expRef] = portRes;
      const rootPid = portId(rootId, expDir, expRef);
      if (!root.ports.some((p) => p.id === rootPid)) {
        root.ports.push(makePort(rootId, expDir, expRef));
      }
      connPortId = rootPid;
    }

    if (!connPortId) continue;

    if (expDir! === "requires") {
      const termId = `terminal.req.${irefLabel(expRef!)}`;
      const termPortId = `${termId}.port`;
      const key = `${termPortId}||${connPortId}`;
      if (!seenPortPairs.has(key)) {
        seenPortPairs.add(key);
        edges.push({
          id: `edge.${termPortId}--${connPortId}`,
          source_port_id: termPortId,
          target_port_id: connPortId,
          label: irefLabel(expRef!),
          interface_name: expRef!.name,
          interface_version: expRef!.version,
        });
      }
    } else {
      const termId = `terminal.prov.${irefLabel(expRef!)}`;
      const termPortId = `${termId}.port`;
      const key = `${connPortId}||${termPortId}`;
      if (!seenPortPairs.has(key)) {
        seenPortPairs.add(key);
        edges.push({
          id: `edge.${connPortId}--${termPortId}`,
          source_port_id: connPortId,
          target_port_id: termPortId,
          label: irefLabel(expRef!),
          interface_name: expRef!.name,
          interface_version: expRef!.version,
        });
      }
    }
  }

  return {
    id: `diagram.${rootId}`,
    title: entity.title || entity.name,
    description: entity.description,
    root,
    peripheral_nodes: peripheralNodes,
    edges,
  };
}

export function buildVizDiagramAll(
  archFiles: Record<string, ArchFileJson>,
  depth: number | null = null,
): VizDiagram {
  const rootId = "all";
  type ExpMap = ExposeMap;

  const opaquNodeMap = new Map<string, VizNode>();
  const allSubEntityMap = new Map<string, ComponentJson | SystemJson | UserDefJson>();
  const expandedBoundaryMap = new Map<string, VizBoundary>();
  const expandedExposeMaps = new Map<string, ExpMap>();
  let allInnerEdges: VizEdge[] = [];
  const allConnects: ConnectDefJson[] = [];

  const entityDepth = depth === null ? null : Math.max(depth - 1, 0);

  for (const archFile of Object.values(archFiles)) {
    for (const comp of archFile.components) {
      const entityPath = comp.qualified_name || comp.name;
      allSubEntityMap.set(comp.name, comp);
      if (shouldExpandEntity(comp) && (depth === null || depth >= 1)) {
        const [bnd, innerEdges, exposeMap] = buildRecursiveBoundary(comp, entityPath, entityDepth);
        expandedBoundaryMap.set(comp.name, bnd);
        expandedExposeMaps.set(comp.name, exposeMap);
        allInnerEdges = allInnerEdges.concat(innerEdges);
      } else {
        opaquNodeMap.set(comp.name, makeChildNode(comp, entityPath));
      }
    }
    for (const sys of archFile.systems) {
      const entityPath = sys.qualified_name || sys.name;
      allSubEntityMap.set(sys.name, sys);
      if (shouldExpandEntity(sys) && (depth === null || depth >= 1)) {
        const [bnd, innerEdges, exposeMap] = buildRecursiveBoundary(sys, entityPath, entityDepth);
        expandedBoundaryMap.set(sys.name, bnd);
        expandedExposeMaps.set(sys.name, exposeMap);
        allInnerEdges = allInnerEdges.concat(innerEdges);
      } else {
        opaquNodeMap.set(sys.name, makeChildNode(sys, entityPath));
      }
    }
    for (const user of archFile.users) {
      const entityPath = user.qualified_name || user.name;
      allSubEntityMap.set(user.name, user);
      opaquNodeMap.set(user.name, makeChildNode(user, entityPath));
    }
    allConnects.push(...archFile.connects);
  }

  const channelNodeMap = collectChannelNodes(allConnects, rootId, allSubEntityMap);

  const allChildren: (VizNode | VizBoundary)[] = [
    ...opaquNodeMap.values(),
    ...expandedBoundaryMap.values(),
    ...channelNodeMap.values(),
  ];
  const root: VizBoundary = {
    id: rootId,
    label: "Architecture",
    title: null,
    kind: "system",
    entity_path: "",
    ports: [],
    tags: [],
    children: allChildren,
  };

  const edges: VizEdge[] = [];
  const seenPortPairs = new Set<string>();

  function addEdge(edge: VizEdge): void {
    const key = `${edge.source_port_id}||${edge.target_port_id}`;
    if (!seenPortPairs.has(key)) {
      seenPortPairs.add(key);
      edges.push(edge);
    }
  }

  for (const edge of allInnerEdges) addEdge(edge);

  for (const conn of allConnects) {
    for (const edge of buildEdgesFromConnectExpanded(
      conn,
      opaquNodeMap,
      expandedBoundaryMap,
      allSubEntityMap,
      channelNodeMap,
      expandedExposeMaps,
    )) {
      addEdge(edge);
    }
  }

  return {
    id: "diagram.all",
    title: "Architecture",
    description: null,
    root,
    peripheral_nodes: [],
    edges,
  };
}

// ─── Internal helpers ─────────────────────────────────────────────────────────

// ExposeMap: port-name → [leaf_node, leaf_entity, leaf_port]
type ExposeMap = Map<string, [VizNode | VizBoundary, ComponentJson | SystemJson | UserDefJson, string]>;

function isSystem(e: ComponentJson | SystemJson | UserDefJson): e is SystemJson {
  return "systems" in e;
}

function isUser(e: ComponentJson | SystemJson | UserDefJson): e is UserDefJson {
  return !("components" in e);
}

function makeId(entityPath: string): string {
  return entityPath.replace(/::/g, "__");
}

function irefLabel(ref: InterfaceRefJson): string {
  return ref.version ? `${ref.name}@${ref.version}` : ref.name;
}

function portId(nodeId: string, direction: "requires" | "provides", ref: InterfaceRefJson): string {
  const dirTag = direction === "requires" ? "req" : "prov";
  const suffix = ref.version ? `${ref.name}@${ref.version}` : ref.name;
  return `${nodeId}.${dirTag}.${suffix}`;
}

function makePort(
  nodeId: string,
  direction: "requires" | "provides",
  ref: InterfaceRefJson,
): VizPort {
  return {
    id: portId(nodeId, direction, ref),
    node_id: nodeId,
    interface_name: ref.name,
    interface_version: ref.version,
    direction,
  };
}

function makePorts(nodeId: string, entity: ComponentJson | SystemJson | UserDefJson): VizPort[] {
  const ports: VizPort[] = [];
  for (const ref of entity.requires) ports.push(makePort(nodeId, "requires", ref));
  for (const ref of entity.provides) ports.push(makePort(nodeId, "provides", ref));
  return ports;
}

function makeChildNode(
  entity: ComponentJson | SystemJson | UserDefJson,
  entityPath: string,
): VizNode {
  const nodeId = makeId(entityPath);
  let kind: NodeKind;
  if (isSystem(entity)) {
    kind = entity.is_external ? "external_system" : "system";
  } else if (isUser(entity)) {
    kind = entity.is_external ? "external_user" : "user";
  } else {
    kind = (entity as ComponentJson).is_external ? "external_component" : "component";
  }
  return {
    id: nodeId,
    label: entity.name,
    title: entity.title,
    kind,
    entity_path: entityPath,
    description: entity.description,
    tags: [...entity.tags],
    ports: makePorts(nodeId, entity),
  };
}

function makeTerminalNode(
  ref: InterfaceRefJson,
  direction: "requires" | "provides",
  kind: NodeKind = "terminal",
  title: string | null = null,
): VizNode {
  const label = irefLabel(ref);
  const dirTag = direction === "requires" ? "req" : "prov";
  const nodeId = `terminal.${dirTag}.${label}`;
  const portDirection: "requires" | "provides" =
    direction === "requires" ? "provides" : "requires";
  const port: VizPort = {
    id: `${nodeId}.port`,
    node_id: nodeId,
    interface_name: ref.name,
    interface_version: ref.version,
    direction: portDirection,
  };
  return { id: nodeId, label, title, kind, entity_path: "", tags: [], ports: [port] };
}

function shouldExpandEntity(entity: ComponentJson | SystemJson | UserDefJson): boolean {
  if (isUser(entity)) return false;
  if ((entity as ComponentJson | SystemJson).is_external) return false;
  if (isSystem(entity)) {
    const s = entity as SystemJson;
    return s.components.length > 0 || s.systems.length > 0 || s.users.length > 0;
  }
  return (entity as ComponentJson).components.length > 0;
}

function findRefByPortName(
  entity: ComponentJson | SystemJson | UserDefJson,
  portName: string,
): ["requires" | "provides", InterfaceRefJson] | null {
  for (const ref of entity.requires) {
    const effective = ref.port_name ?? ref.name;
    if (effective === portName) return ["requires", ref];
  }
  for (const ref of entity.provides) {
    const effective = ref.port_name ?? ref.name;
    if (effective === portName) return ["provides", ref];
  }
  return null;
}

function resolvePortRef(
  entity: ComponentJson | SystemJson | UserDefJson,
  portName: string,
): ["requires" | "provides", InterfaceRefJson] | null {
  const direct = findRefByPortName(entity, portName);
  if (direct) return direct;
  if (!isUser(entity)) {
    const ent = entity as ComponentJson | SystemJson;
    for (const exp of ent.exposes) {
      const effective = exp.as_name ?? exp.port;
      if (effective !== portName) continue;
      let subEnt: ComponentJson | SystemJson | UserDefJson | undefined;
      for (const c of ent.components) {
        if (c.name === exp.entity) { subEnt = c; break; }
      }
      if (!subEnt && isSystem(ent)) {
        for (const s of (ent as SystemJson).systems) {
          if (s.name === exp.entity) { subEnt = s; break; }
        }
        if (!subEnt) {
          for (const u of (ent as SystemJson).users) {
            if (u.name === exp.entity) { subEnt = u; break; }
          }
        }
      }
      if (subEnt) return resolvePortRef(subEnt, exp.port);
    }
  }
  return null;
}

function findPortId(
  node: VizNode | VizBoundary,
  direction: "requires" | "provides",
  ref: InterfaceRefJson,
): string | null {
  for (const p of node.ports) {
    if (p.direction === direction && p.interface_name === ref.name && p.interface_version === ref.version) {
      return p.id;
    }
  }
  return null;
}

function findChannelForPort(
  entityName: string,
  direction: "requires" | "provides",
  interfaceName: string,
  connects: ConnectDefJson[],
): string | null {
  for (const conn of connects) {
    if (!conn.channel) continue;
    if (direction === "provides" && conn.src_entity === entityName) {
      if (conn.src_port === null || conn.src_port === interfaceName) return conn.channel;
    }
    if (direction === "requires" && conn.dst_entity === entityName) {
      if (conn.dst_port === null || conn.dst_port === interfaceName) return conn.channel;
    }
  }
  return null;
}

function collectChannelNodes(
  connects: ConnectDefJson[],
  rootId: string,
  subEntityMap: Map<string, ComponentJson | SystemJson | UserDefJson>,
): Map<string, VizNode> {
  const channelInterfaces = new Map<string, string | null>();
  for (const conn of connects) {
    if (!conn.channel) continue;
    const ch = conn.channel;
    if (!channelInterfaces.has(ch)) channelInterfaces.set(ch, null);
    if (channelInterfaces.get(ch) !== null) continue;
    if (conn.src_entity && conn.src_port) {
      const sub = subEntityMap.get(conn.src_entity);
      if (sub) {
        const res = findRefByPortName(sub, conn.src_port);
        if (res) { channelInterfaces.set(ch, irefLabel(res[1])); continue; }
      }
    }
    if (channelInterfaces.get(ch) === null && conn.dst_entity && conn.dst_port) {
      const sub = subEntityMap.get(conn.dst_entity);
      if (sub) {
        const res = findRefByPortName(sub, conn.dst_port);
        if (res) channelInterfaces.set(ch, irefLabel(res[1]));
      }
    }
  }
  const result = new Map<string, VizNode>();
  for (const [chName, ifaceLabel] of channelInterfaces) {
    const chId = `${rootId}.channel.${chName}`;
    const displayIface = ifaceLabel ?? chName;
    result.set(chName, {
      id: chId, label: chName, title: ifaceLabel, kind: "channel", entity_path: "", tags: [],
      ports: [
        { id: `${chId}.in`, node_id: chId, interface_name: displayIface, interface_version: null, direction: "requires" },
        { id: `${chId}.out`, node_id: chId, interface_name: displayIface, interface_version: null, direction: "provides" },
      ],
    });
  }
  return result;
}

function resolveIfaceLabel(
  entityName: string,
  portName: string,
  subEntityMap: Map<string, ComponentJson | SystemJson | UserDefJson>,
  childExposeMaps: Map<string, ExposeMap>,
): string | null {
  const exposeMap = childExposeMaps.get(entityName);
  if (exposeMap) {
    const inner = exposeMap.get(portName);
    if (inner) {
      const [, leafEntity, leafPort] = inner;
      const res = findRefByPortName(leafEntity, leafPort);
      if (res) return irefLabel(res[1]);
    }
  } else {
    const sub = subEntityMap.get(entityName);
    if (sub) {
      const res = findRefByPortName(sub, portName);
      if (res) return irefLabel(res[1]);
    }
  }
  return null;
}

function collectChannelNodesResolve(
  connects: ConnectDefJson[],
  rootId: string,
  subEntityMap: Map<string, ComponentJson | SystemJson | UserDefJson>,
  opaquNodeMap: Map<string, VizNode>,
  childExposeMaps: Map<string, ExposeMap>,
): Map<string, VizNode> {
  const channelInterfaces = new Map<string, string | null>();
  for (const conn of connects) {
    if (!conn.channel) continue;
    const ch = conn.channel;
    if (!channelInterfaces.has(ch)) channelInterfaces.set(ch, null);
    if (channelInterfaces.get(ch) !== null) continue;
    if (conn.src_entity && conn.src_port) {
      const label = resolveIfaceLabel(conn.src_entity, conn.src_port, subEntityMap, childExposeMaps);
      if (label) { channelInterfaces.set(ch, label); continue; }
    }
    if (channelInterfaces.get(ch) === null && conn.dst_entity && conn.dst_port) {
      const label = resolveIfaceLabel(conn.dst_entity, conn.dst_port, subEntityMap, childExposeMaps);
      if (label) channelInterfaces.set(ch, label);
    }
  }
  const result = new Map<string, VizNode>();
  for (const [chName, ifaceLabel] of channelInterfaces) {
    const chId = `${rootId}.channel.${chName}`;
    const displayIface = ifaceLabel ?? chName;
    result.set(chName, {
      id: chId, label: chName, title: ifaceLabel, kind: "channel", entity_path: "", tags: [],
      ports: [
        { id: `${chId}.in`, node_id: chId, interface_name: displayIface, interface_version: null, direction: "requires" },
        { id: `${chId}.out`, node_id: chId, interface_name: displayIface, interface_version: null, direction: "provides" },
      ],
    });
  }
  return result;
}

type ResolveSideFn = (
  entityName: string | null,
  portName: string | null,
) => [VizNode | VizBoundary, ComponentJson | SystemJson | UserDefJson, string] | null;

function buildEdgesForConnect(
  conn: ConnectDefJson,
  channelNodeMap: Map<string, VizNode>,
  resolveSide: ResolveSideFn,
): VizEdge[] {
  if (!conn.channel) {
    if (!conn.src_entity || !conn.src_port || !conn.dst_entity || !conn.dst_port) return [];
    const src = resolveSide(conn.src_entity, conn.src_port);
    const dst = resolveSide(conn.dst_entity, conn.dst_port);
    if (!src || !dst) return [];
    const [srcNode, srcSub, srcEff] = src;
    const [dstNode, dstSub, dstEff] = dst;
    const srcResult = resolvePortRef(srcSub, srcEff);
    const dstResult = resolvePortRef(dstSub, dstEff);
    if (!srcResult || !dstResult) return [];
    const [srcDir, srcRef] = srcResult;
    const [dstDir, dstRef] = dstResult;
    let srcPortId = findPortId(srcNode, srcDir, srcRef);
    if (!srcPortId) {
      const p = makePort(srcNode.id, srcDir, srcRef);
      srcNode.ports.push(p);
      srcPortId = p.id;
    }
    let dstPortId = findPortId(dstNode, dstDir, dstRef);
    if (!dstPortId) {
      const p = makePort(dstNode.id, dstDir, dstRef);
      dstNode.ports.push(p);
      dstPortId = p.id;
    }
    return [{
      id: `edge.${srcPortId}--${dstPortId}`,
      source_port_id: srcPortId,
      target_port_id: dstPortId,
      label: irefLabel(srcRef),
      interface_name: srcRef.name,
      interface_version: srcRef.version,
    }];
  }

  const chNode = channelNodeMap.get(conn.channel);
  if (!chNode) return [];
  const chInPort = chNode.ports.find((p) => p.direction === "requires") ?? null;
  const chOutPort = chNode.ports.find((p) => p.direction === "provides") ?? null;
  const edges: VizEdge[] = [];

  if (conn.src_entity && conn.src_port && chInPort) {
    const src = resolveSide(conn.src_entity, conn.src_port);
    if (src) {
      const [srcNode, srcSub, srcEff] = src;
      const srcResult = resolvePortRef(srcSub, srcEff);
      if (srcResult) {
        const [srcDir, srcRef] = srcResult;
        let srcPortId = findPortId(srcNode, srcDir, srcRef);
        if (!srcPortId) {
          const p = makePort(srcNode.id, srcDir, srcRef);
          srcNode.ports.push(p);
          srcPortId = p.id;
        }
        edges.push({
          id: `edge.${srcPortId}--${chInPort.id}`,
          source_port_id: srcPortId,
          target_port_id: chInPort.id,
          label: irefLabel(srcRef),
          interface_name: srcRef.name,
          interface_version: srcRef.version,
        });
      }
    }
  }
  if (conn.dst_entity && conn.dst_port && chOutPort) {
    const dst = resolveSide(conn.dst_entity, conn.dst_port);
    if (dst) {
      const [dstNode, dstSub, dstEff] = dst;
      const dstResult = resolvePortRef(dstSub, dstEff);
      if (dstResult) {
        const [dstDir, dstRef] = dstResult;
        let dstPortId = findPortId(dstNode, dstDir, dstRef);
        if (!dstPortId) {
          const p = makePort(dstNode.id, dstDir, dstRef);
          dstNode.ports.push(p);
          dstPortId = p.id;
        }
        edges.push({
          id: `edge.${chOutPort.id}--${dstPortId}`,
          source_port_id: chOutPort.id,
          target_port_id: dstPortId,
          label: irefLabel(dstRef),
          interface_name: dstRef.name,
          interface_version: dstRef.version,
        });
      }
    }
  }
  return edges;
}

function buildEdgesFromConnectResolve(
  conn: ConnectDefJson,
  opaquNodeMap: Map<string, VizNode>,
  expandedBoundaryMap: Map<string, VizBoundary>,
  subEntityMap: Map<string, ComponentJson | SystemJson | UserDefJson>,
  channelNodeMap: Map<string, VizNode>,
  childExposeMaps: Map<string, ExposeMap>,
): VizEdge[] {
  function resolveSide(
    entityName: string | null,
    portName: string | null,
  ): [VizNode | VizBoundary, ComponentJson | SystemJson | UserDefJson, string] | null {
    if (!entityName || !portName) return null;
    const entity = subEntityMap.get(entityName);
    if (!entity) return null;
    const exposeMap = childExposeMaps.get(entityName);
    if (exposeMap !== undefined) {
      const inner = exposeMap.get(portName);
      if (inner) return inner;
      const bnd = expandedBoundaryMap.get(entityName);
      if (bnd) return [bnd, entity, portName];
    }
    const node = opaquNodeMap.get(entityName);
    if (node) return [node, entity, portName];
    return null;
  }
  return buildEdgesForConnect(conn, channelNodeMap, resolveSide);
}

function buildEdgesFromConnectExpanded(
  conn: ConnectDefJson,
  opaquNodeMap: Map<string, VizNode>,
  expandedBoundaryMap: Map<string, VizBoundary>,
  allEntityMap: Map<string, ComponentJson | SystemJson | UserDefJson>,
  channelNodeMap: Map<string, VizNode>,
  expandedExposeMaps: Map<string, ExposeMap>,
): VizEdge[] {
  function resolveSide(
    entityName: string | null,
    portName: string | null,
  ): [VizNode | VizBoundary, ComponentJson | SystemJson | UserDefJson, string] | null {
    if (!entityName || !portName) return null;
    const entity = allEntityMap.get(entityName);
    if (!entity) return null;
    const exposeMap = expandedExposeMaps.get(entityName);
    if (exposeMap !== undefined) {
      const inner = exposeMap.get(portName);
      if (inner) return inner;
      const bnd = expandedBoundaryMap.get(entityName);
      if (bnd) return [bnd, entity, portName];
    }
    const node = opaquNodeMap.get(entityName);
    if (node) return [node, entity, portName];
    return null;
  }
  return buildEdgesForConnect(conn, channelNodeMap, resolveSide);
}

function buildRecursiveBoundary(
  entity: ComponentJson | SystemJson,
  entityPath: string,
  remainingDepth: number | null = null,
): [VizBoundary, VizEdge[], ExposeMap] {
  const rootId = makeId(entityPath);

  const childEntities: (ComponentJson | SystemJson | UserDefJson)[] = [...entity.components];
  if (isSystem(entity)) {
    childEntities.push(...entity.systems, ...entity.users);
  }

  const subEntityMap = new Map<string, ComponentJson | SystemJson | UserDefJson>();
  const opaquNodeMap = new Map<string, VizNode>();
  const childBoundaryMap = new Map<string, VizBoundary>();
  const childExposeMaps = new Map<string, ExposeMap>();
  let allEdges: VizEdge[] = [];

  for (const child of childEntities) {
    const childPath = `${entityPath}::${child.name}`;
    subEntityMap.set(child.name, child);
    if (
      !isUser(child) &&
      shouldExpandEntity(child) &&
      (remainingDepth === null || remainingDepth > 0)
    ) {
      const nextDepth = remainingDepth === null ? null : remainingDepth - 1;
      const [childBnd, childEdges, childExposeMap] = buildRecursiveBoundary(
        child as ComponentJson | SystemJson,
        childPath,
        nextDepth,
      );
      childBoundaryMap.set(child.name, childBnd);
      childExposeMaps.set(child.name, childExposeMap);
      allEdges = allEdges.concat(childEdges);
    } else {
      opaquNodeMap.set(child.name, makeChildNode(child, childPath));
    }
  }

  const channelNodeMap = collectChannelNodesResolve(
    entity.connects,
    rootId,
    subEntityMap,
    opaquNodeMap,
    childExposeMaps,
  );

  const allChildren: (VizNode | VizBoundary)[] = [
    ...opaquNodeMap.values(),
    ...childBoundaryMap.values(),
    ...channelNodeMap.values(),
  ];
  const boundary: VizBoundary = {
    id: rootId,
    label: entity.name,
    title: entity.title,
    kind: isSystem(entity) ? "system" : ("component" as BoundaryKind),
    entity_path: entityPath,
    description: entity.description,
    tags: [...entity.tags],
    ports: makePorts(rootId, entity),
    children: allChildren,
  };

  const seen = new Set<string>();
  for (const conn of entity.connects) {
    for (const edge of buildEdgesFromConnectResolve(
      conn, opaquNodeMap, childBoundaryMap, subEntityMap, channelNodeMap, childExposeMaps,
    )) {
      const key = `${edge.source_port_id}||${edge.target_port_id}`;
      if (!seen.has(key)) {
        seen.add(key);
        allEdges.push(edge);
      }
    }
  }

  // Build expose map for this entity's own exposed ports
  const exposeMap: ExposeMap = new Map();
  for (const exp of entity.exposes) {
    const effective = exp.as_name ?? exp.port;
    const childEntity = subEntityMap.get(exp.entity);
    if (!childEntity) continue;
    if (childExposeMaps.has(exp.entity)) {
      const inner = childExposeMaps.get(exp.entity)!.get(exp.port);
      if (inner) exposeMap.set(effective, inner);
    } else {
      const childNode = opaquNodeMap.get(exp.entity);
      if (childNode) exposeMap.set(effective, [childNode, childEntity, exp.port]);
    }
  }

  return [boundary, allEdges, exposeMap];
}

// Helpers used in layout.ts
export { makeId, irefLabel, isBoundary };
export type { ExposeMap };

export function collectInnerNodes(boundary: VizBoundary): VizNode[] {
  const result: VizNode[] = [];
  for (const child of boundary.children) {
    if (isBoundary(child)) result.push(...collectInnerNodes(child));
    else result.push(child);
  }
  return result;
}

export function collectPorts(boundary: VizBoundary): Map<string, string> {
  const result = new Map<string, string>();
  for (const port of boundary.ports) result.set(port.id, boundary.id);
  for (const child of boundary.children) {
    if (isBoundary(child)) {
      for (const [k, v] of collectPorts(child)) result.set(k, v);
    } else {
      for (const port of child.ports) result.set(port.id, child.id);
    }
  }
  return result;
}

export function collectNodeParents(boundary: VizBoundary): Map<string, string> {
  const result = new Map<string, string>();
  for (const child of boundary.children) {
    if (isBoundary(child)) {
      for (const [k, v] of collectNodeParents(child)) result.set(k, v);
    } else {
      result.set(child.id, boundary.id);
    }
  }
  return result;
}

export function collectBoundaryIds(boundary: VizBoundary): Set<string> {
  const result = new Set<string>([boundary.id]);
  for (const child of boundary.children) {
    if (isBoundary(child)) {
      for (const id of collectBoundaryIds(child)) result.add(id);
    }
  }
  return result;
}

export function collectNestedBoundaries(boundary: VizBoundary): VizBoundary[] {
  const result: VizBoundary[] = [];
  for (const child of boundary.children) {
    if (isBoundary(child)) {
      result.push(child);
      result.push(...collectNestedBoundaries(child));
    }
  }
  return result;
}
