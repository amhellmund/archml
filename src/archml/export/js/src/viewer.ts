// Copyright 2026 ArchML Contributors
// SPDX-License-Identifier: Apache-2.0

// Interactive viewer shell: entity selector, depth selector, pan/zoom, sidebar.
// Renders into a provided container element.

import type {
  ArchFileJson,
  ConnectDefJson,
  EntityEntry,
  InterfaceDefJson,
  InterfaceRefJson,
  LayoutPlan,
  SystemJson,
  ComponentJson,
  TypeDefJson,
  TypeRefJson,
  VizDiagram,
  ViewerPayload,
} from "./types";
import { buildVizDiagram, buildVizDiagramAll } from "./topology";
import { computeLayout } from "./layout";
import { renderToSvgString } from "./renderer";

// ─── Public API ───────────────────────────────────────────────────────────────

/** Mount the full interactive viewer into *container*. */
export function mountViewer(container: HTMLElement, payload: ViewerPayload): void {
  const widthOptimized = payload.widthOptimized === true;
  container.innerHTML = buildViewerShell(widthOptimized);
  container.className = widthOptimized ? "archml-viewer archml-viewer--wo" : "archml-viewer";

  const canvasArea = container.querySelector<HTMLElement>(".archml-canvas-area")!;
  const canvasTransform = container.querySelector<HTMLElement>(".archml-canvas-transform")!;
  // In width-optimized mode details are shown in .archml-sidebar-details; otherwise .archml-sidebar-right.
  const detailsSidebar = container.querySelector<HTMLElement>(
    widthOptimized ? ".archml-sidebar-details" : ".archml-sidebar-right",
  )!;
  const entitySelectWrap = container.querySelector<HTMLElement>("#archml-entity-select-wrap")!;
  const depthSelect = container.querySelector<HTMLSelectElement>("#archml-depth-select")!;
  const errorBanner = container.querySelector<HTMLElement>(".archml-error-banner")!;
  const loadingEl = container.querySelector<HTMLElement>(".archml-loading")!;

  // Hamburger toggle (width-optimized mode only)
  if (widthOptimized) {
    const hamburger = container.querySelector<HTMLElement>(".archml-hamburger");
    hamburger?.addEventListener("click", () => {
      container.classList.toggle("archml-viewer--sidebar-collapsed");
    });
  }

  // Build custom entity dropdown
  const customEntitySelect = buildCustomEntitySelect(entitySelectWrap, payload.entities, () => {
    void renderDiagram();
  });

  // Pan/zoom state
  let tx = 0, ty = 0, scale = 1.0;
  let dragging = false, startX = 0, startY = 0, didDrag = false;

  function applyTransform(): void {
    canvasTransform.style.transform = `translate(${tx}px,${ty}px) scale(${scale})`;
  }

  function resetTransform(): void {
    tx = 0; ty = 0; scale = 1.0;
    applyTransform();
  }

  canvasArea.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    dragging = true; didDrag = false;
    startX = e.clientX - tx; startY = e.clientY - ty;
    e.preventDefault();
  });
  document.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    didDrag = true;
    tx = e.clientX - startX; ty = e.clientY - startY;
    applyTransform();
  });
  document.addEventListener("mouseup", () => { dragging = false; });
  canvasArea.addEventListener("wheel", (e) => {
    e.preventDefault();
    const rect = canvasArea.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const factor = e.deltaY > 0 ? 0.9 : 1.1;
    const newScale = Math.max(0.05, Math.min(20.0, scale * factor));
    tx = mx - (mx - tx) * (newScale / scale);
    ty = my - (my - ty) * (newScale / scale);
    scale = newScale;
    applyTransform();
  }, { passive: false });

  // Track the entity currently shown in the diagram (for expose-chain channel lookup).
  let currentEntity: ComponentJson | SystemJson | null = null;

  // Entity click → details sidebar
  canvasArea.addEventListener("click", (e) => {
    if (didDrag) { didDrag = false; return; }
    const target = (e.target as Element).closest(".archml-entity") as HTMLElement | null;
    if (target) {
      const entityPath = target.dataset["entityPath"] ?? "";
      const entityKind = target.dataset["entityKind"] ?? "";
      let channelName = target.dataset["channel"] ?? null;
      if (!channelName && currentEntity && (entityKind === "terminal" || entityKind === "interface")) {
        channelName = findChannelViaExposeChain(payload.files, currentEntity, entityPath);
      }
      showEntityDetails(detailsSidebar, entityPath, entityKind, payload, channelName);
    }
  }, { capture: true });

  // Diagram rendering
  async function renderDiagram(): Promise<void> {
    loadingEl.style.display = "block";
    canvasTransform.innerHTML = "";
    errorBanner.style.display = "none";
    errorBanner.textContent = "";

    const entityValue = customEntitySelect.getValue();
    const depthValue = depthSelect.value;
    const depth: number | null = depthValue === "full" ? null : parseInt(depthValue, 10);

    try {
      let diagram: VizDiagram;
      if (entityValue === "all") {
        currentEntity = null;
        diagram = buildVizDiagramAll(payload.files, depth);
      } else {
        const entity = findEntity(payload.files, entityValue);
        if (!entity) {
          errorBanner.textContent = `Entity not found: ${entityValue}`;
          errorBanner.style.display = "block";
          loadingEl.style.display = "none";
          return;
        }
        currentEntity = entity;
        diagram = buildVizDiagram(entity, depth, collectParentConnects(payload.files, entity));
      }

      const plan: LayoutPlan = await computeLayout(diagram);
      const svg = renderToSvgString(diagram, plan);
      canvasTransform.innerHTML = svg;
      resetTransform();
    } catch (err) {
      errorBanner.textContent = `Render error: ${String(err)}`;
      errorBanner.style.display = "block";
    } finally {
      loadingEl.style.display = "none";
    }
  }

  depthSelect.addEventListener("change", () => { void renderDiagram(); });

  // Initial render
  void renderDiagram();
}

/** Mount a fixed embedded diagram (Sphinx embed mode: no entity selector). */
export function mountEmbed(
  container: HTMLElement,
  payload: ViewerPayload,
  entityPath: string,
  depth: number | null,
): void {
  container.className = "archml-embed";
  container.innerHTML = `<div class="archml-canvas-transform"></div><div class="archml-loading">Loading…</div>`;
  const canvasTransform = container.querySelector<HTMLElement>(".archml-canvas-transform")!;
  const loadingEl = container.querySelector<HTMLElement>(".archml-loading")!;

  let tx = 0, ty = 0, scale = 1.0;
  let dragging = false, sx = 0, sy = 0;

  function applyTransform(): void {
    canvasTransform.style.transform = `translate(${tx}px,${ty}px) scale(${scale})`;
  }

  container.addEventListener("mousedown", (e) => {
    dragging = true; sx = e.clientX - tx; sy = e.clientY - ty; e.preventDefault();
  });
  document.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    tx = e.clientX - sx; ty = e.clientY - sy;
    applyTransform();
  });
  document.addEventListener("mouseup", () => { dragging = false; });
  container.addEventListener("wheel", (e) => {
    e.preventDefault();
    const rect = container.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const factor = e.deltaY > 0 ? 0.9 : 1.1;
    const newScale = Math.max(0.05, Math.min(20.0, scale * factor));
    tx = mx - (mx - tx) * (newScale / scale);
    ty = my - (my - ty) * (newScale / scale);
    scale = newScale;
    applyTransform();
  }, { passive: false });

  async function render(): Promise<void> {
    try {
      let diagram: VizDiagram;
      if (entityPath === "all") {
        diagram = buildVizDiagramAll(payload.files, depth);
      } else {
        const entity = findEntity(payload.files, entityPath);
        if (!entity) throw new Error(`Entity not found: ${entityPath}`);
        diagram = buildVizDiagram(entity, depth, collectParentConnects(payload.files, entity));
      }
      const plan = await computeLayout(diagram);
      canvasTransform.innerHTML = renderToSvgString(diagram, plan);
      loadingEl.style.display = "none";
    } catch (err) {
      loadingEl.textContent = `Error: ${String(err)}`;
    }
  }

  void render();
}

// ─── Internal helpers ─────────────────────────────────────────────────────────

function buildViewerShell(widthOptimized: boolean): string {
  if (widthOptimized) {
    return `
      <div class="archml-topbar">
        <button class="archml-hamburger" type="button" title="Toggle sidebar">&#9776;</button>
        <span class="archml-topbar-title">ArchML Explorer</span>
      </div>
      <div class="archml-body">
        <div class="archml-sidebar-combined">
          <div class="archml-sidebar-controls">
            <div>
              <label>Entity</label>
              <div id="archml-entity-select-wrap"></div>
            </div>
            <div>
              <label for="archml-depth-select">Depth</label>
              <select id="archml-depth-select">
                <option value="full">Full depth</option>
                <option value="0">0 – root only</option>
                <option value="1">1 – children</option>
                <option value="2">2 – grand children</option>
              </select>
            </div>
            <div class="archml-error-banner" style="display:none"></div>
          </div>
          <div class="archml-sidebar-details">
            <p class="archml-detail-empty">Click an entity to see details.</p>
          </div>
        </div>
        <div class="archml-canvas-area">
          <div class="archml-canvas-transform"></div>
          <div class="archml-loading">Loading…</div>
        </div>
      </div>
    `.trim();
  }
  return `
    <div class="archml-sidebar-left">
      <div>
        <label>Entity</label>
        <div id="archml-entity-select-wrap"></div>
      </div>
      <div>
        <label for="archml-depth-select">Depth</label>
        <select id="archml-depth-select">
          <option value="full">Full depth</option>
          <option value="0">0 – root only</option>
          <option value="1">1 – children</option>
          <option value="2">2 – grand children</option>
        </select>
      </div>
      <div class="archml-error-banner" style="display:none"></div>
    </div>
    <div class="archml-canvas-area">
      <div class="archml-canvas-transform"></div>
      <div class="archml-loading">Loading…</div>
    </div>
    <div class="archml-sidebar-right">
      <p class="archml-detail-empty">Click an entity to see details.</p>
    </div>
  `.trim();
}

// Color scheme matching archml-diagram.css node/boundary classes.
const KIND_COLORS: Record<string, { bg: string; border: string }> = {
  system:             { bg: "#eff6ff", border: "#2563eb" },
  external_system:    { bg: "#f8fafc", border: "#475569" },
  component:          { bg: "#fff7ed", border: "#ea580c" },
  external_component: { bg: "#f8fafc", border: "#475569" },
};

function makeKindDot(kind: string | null): HTMLSpanElement {
  const dot = document.createElement("span");
  dot.className = "archml-kind-dot";
  const c = kind ? (KIND_COLORS[kind] ?? null) : null;
  if (c) {
    dot.style.background = c.bg;
    dot.style.borderColor = c.border;
  } else {
    dot.style.background = "#e2e8f0";
    dot.style.borderColor = "#94a3b8";
  }
  return dot;
}

function buildCustomEntitySelect(
  container: HTMLElement,
  entities: EntityEntry[],
  onChange: () => void,
): { getValue: () => string } {
  let currentValue = "all";
  let isOpen = false;

  container.className = "archml-custom-select";

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "archml-custom-select__trigger";

  const panel = document.createElement("div");
  panel.className = "archml-custom-select__panel";
  panel.hidden = true;

  container.appendChild(trigger);
  container.appendChild(panel);

  function setTriggerContent(label: string, kind: string | null): void {
    trigger.innerHTML = "";
    trigger.appendChild(makeKindDot(kind));
    const span = document.createElement("span");
    span.className = "archml-custom-select__label";
    span.textContent = label;
    trigger.appendChild(span);
    const arrow = document.createElement("span");
    arrow.className = "archml-custom-select__arrow";
    arrow.textContent = "▾";
    trigger.appendChild(arrow);
  }

  function close(): void {
    isOpen = false;
    panel.hidden = true;
    trigger.classList.remove("is-open");
  }

  function addOption(value: string, label: string, kind: string | null): void {
    const opt = document.createElement("div");
    opt.className = "archml-custom-select__option";
    opt.appendChild(makeKindDot(kind));
    const span = document.createElement("span");
    span.textContent = label;
    opt.appendChild(span);
    opt.addEventListener("click", () => {
      currentValue = value;
      setTriggerContent(label, kind);
      close();
      onChange();
    });
    panel.appendChild(opt);
  }

  function addGroupLabel(text: string): void {
    const lbl = document.createElement("div");
    lbl.className = "archml-custom-select__group";
    lbl.textContent = text;
    panel.appendChild(lbl);
  }

  // Build options
  addOption("all", "All entities", null);

  const systems = entities.filter((e) => e.kind === "system" || e.kind === "external_system");
  const components = entities.filter((e) => e.kind === "component" || e.kind === "external_component");

  if (systems.length > 0) {
    addGroupLabel("Systems");
    for (const e of systems) {
      addOption(e.qualified_name, e.title ? `${e.qualified_name} — ${e.title}` : e.qualified_name, e.kind);
    }
  }
  if (components.length > 0) {
    addGroupLabel("Components");
    for (const e of components) {
      addOption(e.qualified_name, e.title ? `${e.qualified_name} — ${e.title}` : e.qualified_name, e.kind);
    }
  }

  setTriggerContent("All entities", null);

  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    isOpen = !isOpen;
    panel.hidden = !isOpen;
    trigger.classList.toggle("is-open", isOpen);
  });

  document.addEventListener("click", () => { if (isOpen) close(); });

  return { getValue: () => currentValue };
}

function findEntity(
  files: Record<string, ArchFileJson>,
  qualifiedName: string,
): ComponentJson | SystemJson | null {
  for (const archFile of Object.values(files)) {
    for (const sys of archFile.systems) {
      const found = _findInSystem(sys, qualifiedName);
      if (found) return found;
    }
    for (const comp of archFile.components) {
      const found = _findInComponent(comp, qualifiedName);
      if (found) return found;
    }
  }
  return null;
}

function _findInSystem(sys: SystemJson, qualifiedName: string): SystemJson | ComponentJson | null {
  if (sys.qualified_name === qualifiedName) return sys;
  for (const sub of sys.systems) {
    const found = _findInSystem(sub, qualifiedName);
    if (found) return found;
  }
  for (const comp of sys.components) {
    const found = _findInComponent(comp, qualifiedName);
    if (found) return found;
  }
  return null;
}

function _findInComponent(comp: ComponentJson, qualifiedName: string): ComponentJson | null {
  if (comp.qualified_name === qualifiedName) return comp;
  for (const sub of comp.components) {
    const found = _findInComponent(sub, qualifiedName);
    if (found) return found;
  }
  return null;
}

function showEntityDetails(
  sidebar: HTMLElement,
  entityPath: string,
  entityKind: string,
  payload: ViewerPayload,
  channelName: string | null = null,
): void {
  if (!entityPath) {
    sidebar.innerHTML = `<p class="archml-detail-empty">Click an entity to see details.</p>`;
    return;
  }

  // Interface, terminal, and channel nodes show the interface type tree.
  if (entityKind === "interface" || entityKind === "terminal" || entityKind === "channel") {
    showInterfaceDetails(sidebar, entityPath, payload.files, channelName);
    return;
  }

  const entity = findEntity(payload.files, entityPath);
  const title = entity?.title ?? entityPath.split("::").pop() ?? entityPath;
  const description = entity?.description ?? null;
  const tags: string[] = entity?.tags ?? [];
  const requires = entity?.requires ?? [];
  const provides = entity?.provides ?? [];
  const kindLabel = entityKind.replace(/_/g, " ");

  let html = `
    <h3 class="archml-detail-title">${escText(title)}</h3>
    <div class="archml-detail-kind">${escText(kindLabel)}</div>
  `;

  {
    let generalBody = "";
    if (description) generalBody += `<p class="archml-detail-description">${escText(description)}</p>`;
    if (tags.length > 0) generalBody += `<div class="archml-detail-tags">${tags.map((t) => `<span class="archml-detail-pill">${escText(t)}</span>`).join("")}</div>`;
    if (generalBody) html += detailsSection("general", generalBody);
  }

  html += renderIfaceSection("Requires", requires, payload.files);
  html += renderIfaceSection("Provides", provides, payload.files);

  sidebar.innerHTML = html;
}

/**
 * Walk the expose chain upward from *entity* to find the channel associated
 * with *interfaceName*. Checks the parent's connects at each level using the
 * entity name visible at that scope, following expose re-exports as needed.
 *
 * Direction-aware: determines whether the interface is a "requires" (entity is
 * the connect destination) or "provides" (entity is the connect source) port
 * so that entity-level connects with null ports don't cause false positives.
 */
function findChannelViaExposeChain(
  files: Record<string, ArchFileJson>,
  entity: ComponentJson | SystemJson,
  interfaceName: string,
): string | null {
  // Strip version suffix for port name comparison.
  const baseName = interfaceName.includes("@") ? interfaceName.split("@")[0] : interfaceName;

  // Determine direction from the entity's own requires/provides lists.
  let direction: "requires" | "provides" | null = null;
  for (const ref of entity.requires) {
    if (ref.name === baseName || (ref.port_name ?? ref.name) === baseName) {
      direction = "requires"; break;
    }
  }
  if (!direction) {
    for (const ref of entity.provides) {
      if (ref.name === baseName || (ref.port_name ?? ref.name) === baseName) {
        direction = "provides"; break;
      }
    }
  }

  let entityName = entity.name;
  let qualName = entity.qualified_name || entity.name;
  let portName = baseName;

  while (true) {
    const lastSep = qualName.lastIndexOf("::");
    let parentConnects: ConnectDefJson[];
    let parentEntity: ComponentJson | SystemJson | null = null;

    if (lastSep !== -1) {
      const parentPath = qualName.slice(0, lastSep);
      parentEntity = findEntity(files, parentPath);
      // When parentPath is a file-namespace key (no matching entity), fall back
      // to file-level connects — same as the else branch below.
      parentConnects = parentEntity
        ? parentEntity.connects
        : Object.values(files).flatMap((af) => af.connects);
    } else {
      parentConnects = Object.values(files).flatMap((af) => af.connects);
    }

    // Search for a connect routing entityName.portName through a channel.
    // Use direction to avoid false positives from entity-level connects (null ports):
    // "requires" means the entity is a destination; "provides" means it is a source.
    for (const conn of parentConnects) {
      if (!conn.channel) continue;
      if (direction !== "provides") {
        // Check entity as destination (covers "requires" and unknown direction).
        if (conn.dst_entity === entityName && (conn.dst_port === null || conn.dst_port === portName)) {
          return conn.channel;
        }
      }
      if (direction !== "requires") {
        // Check entity as source (covers "provides" and unknown direction).
        if (conn.src_entity === entityName && (conn.src_port === null || conn.src_port === portName)) {
          return conn.channel;
        }
      }
    }

    // Not found at this level — check whether the parent re-exposes this interface.
    if (!parentEntity) break;
    let nextPortName: string | null = null;
    for (const exp of parentEntity.exposes) {
      if (exp.entity === entityName && (exp.port === portName || (exp.as_name ?? exp.port) === portName)) {
        nextPortName = exp.as_name ?? exp.port;
        break;
      }
    }
    if (!nextPortName) break;

    entityName = parentEntity.name;
    qualName = parentEntity.qualified_name || parentEntity.name;
    portName = nextPortName;
    // direction is preserved: a re-exported requires stays requires at every level.
  }

  return null;
}

/**
 * Return the connect statements from the parent scope of *entity*.
 * These are the connects that reference this entity by its short name as
 * src_entity / dst_entity, and therefore carry the channel information that
 * `findChannelForPort` needs to annotate terminal nodes.
 *
 * Strategy: strip the last `::segment` from the qualified_name to get the
 * parent path, look it up as an entity, and return its connects.  If the
 * parent is not a navigable entity (e.g. it is the file-level scope), fall
 * back to the file-level connects of every file.
 */
function collectParentConnects(
  files: Record<string, ArchFileJson>,
  entity: ComponentJson | SystemJson,
): ConnectDefJson[] {
  const qualName = entity.qualified_name || entity.name;
  const lastSep = qualName.lastIndexOf("::");
  if (lastSep !== -1) {
    const parentPath = qualName.slice(0, lastSep);
    const parent = findEntity(files, parentPath);
    if (parent) return (parent as ComponentJson | SystemJson).connects ?? [];
  }
  // Top-level entity — parent scope is the file level.
  return Object.values(files).flatMap((af) => af.connects);
}

function showInterfaceDetails(
  sidebar: HTMLElement,
  ifaceName: string,
  files: Record<string, ArchFileJson>,
  channelName: string | null = null,
): void {
  const def = findInterfaceDef(files, ifaceName);

  // Channel node with no resolved interface definition — show channel name and kind.
  if (!def) {
    sidebar.innerHTML = `
      <h3 class="archml-detail-title">$${escText(ifaceName)}</h3>
      <div class="archml-detail-kind">channel</div>
    `;
    return;
  }

  const label = def.version ? `${def.name}@${def.version}` : def.name;
  let html = `
    <h3 class="archml-detail-title">${escText(def.title ?? def.name)}</h3>
    <div class="archml-detail-kind">interface</div>
  `;

  {
    let generalBody = "";
    if (def.description) generalBody += `<p class="archml-detail-description">${escText(def.description)}</p>`;
    if (def.tags.length > 0) generalBody += `<div class="archml-detail-tags">${def.tags.map((t) => `<span class="archml-detail-pill">${escText(t)}</span>`).join("")}</div>`;
    if (generalBody) html += detailsSection("general", generalBody);
  }

  if (def.fields.length > 0) {
    const fieldsHtml = def.fields
      .map(
        (f) =>
          `<li class="archml-type-field"><span class="archml-type-fname">${escText(f.name)}</span><span class="archml-type-sep">:</span>${renderTypeRef(f.type, files, new Set())}</li>`,
      )
      .join("");
    html += detailsSection("Fields", `<ul class="archml-type-tree">${fieldsHtml}</ul>`);
  }

  if (channelName) {
    html += detailsSection("Channel", `<span class="archml-detail-pill">$${escText(channelName)}</span>`);
  }

  sidebar.innerHTML = html;
}

// ─── Interface + type-tree helpers ────────────────────────────────────────────

function detailsSection(heading: string, body: string, open = true): string {
  return `<details class="archml-detail-section"${open ? " open" : ""}><summary>${escText(heading)}</summary><div class="archml-detail-section-body">${body}</div></details>`;
}

function renderIfaceSection(
  heading: string,
  refs: InterfaceRefJson[],
  files: Record<string, ArchFileJson>,
): string {
  if (refs.length === 0) return "";
  let body = "";
  for (const ref of refs) {
    const label = ref.version ? `${ref.name}@${ref.version}` : ref.name;
    const def = findInterfaceDef(files, ref.name, ref.version);
    if (!def || def.fields.length === 0) {
      body += `<div class="archml-detail-iface">${escText(label)}</div>`;
    } else {
      const fieldsHtml = def.fields
        .map((f) => `<li class="archml-type-field"><span class="archml-type-fname">${escText(f.name)}</span><span class="archml-type-sep">:</span>${renderTypeRef(f.type, files, new Set())}</li>`)
        .join("");
      body += `<details class="archml-iface-block" open><summary>${escText(label)}</summary><div class="archml-iface-block-body"><ul class="archml-type-tree">${fieldsHtml}</ul></div></details>`;
    }
  }
  return detailsSection(heading, body);
}

function findInterfaceDef(
  files: Record<string, ArchFileJson>,
  name: string,
  version: string | null = null,
): InterfaceDefJson | null {
  for (const af of Object.values(files)) {
    const found = searchInterfaces(af.interfaces, name, version)
      ?? af.systems.reduce<InterfaceDefJson | null>((a, s) => a ?? findIfaceInSystem(s, name, version), null)
      ?? af.components.reduce<InterfaceDefJson | null>((a, c) => a ?? findIfaceInComponent(c, name, version), null);
    if (found) return found;
  }
  return null;
}

function searchInterfaces(
  list: InterfaceDefJson[],
  name: string,
  version: string | null,
): InterfaceDefJson | null {
  return list.find(
    (i) => (i.qualified_name === name || i.name === name) && (!version || i.version === version),
  ) ?? null;
}

function findIfaceInSystem(sys: SystemJson, name: string, version: string | null): InterfaceDefJson | null {
  return searchInterfaces(sys.interfaces, name, version)
    ?? sys.systems.reduce<InterfaceDefJson | null>((a, s) => a ?? findIfaceInSystem(s, name, version), null)
    ?? sys.components.reduce<InterfaceDefJson | null>((a, c) => a ?? findIfaceInComponent(c, name, version), null);
}

function findIfaceInComponent(comp: ComponentJson, name: string, version: string | null): InterfaceDefJson | null {
  return searchInterfaces(comp.interfaces, name, version)
    ?? comp.components.reduce<InterfaceDefJson | null>((a, c) => a ?? findIfaceInComponent(c, name, version), null);
}

function findTypeDef(files: Record<string, ArchFileJson>, name: string): TypeDefJson | null {
  for (const af of Object.values(files)) {
    const t = af.types.find((td) => td.name === name);
    if (t) return t;
  }
  return null;
}

function renderTypeRef(type: TypeRefJson, files: Record<string, ArchFileJson>, visited: Set<string>): string {
  switch (type.kind) {
    case "primitive":
      return `<span class="archml-type-primitive">${escText(type.primitive)}</span>`;

    case "optional": {
      const inner = renderTypeRef(type.inner_type, files, visited);
      return `<span class="archml-type-wrapper">optional</span><ul class="archml-type-children"><li>${inner}</li></ul>`;
    }

    case "list": {
      const inner = renderTypeRef(type.element_type, files, visited);
      return `<span class="archml-type-wrapper">List</span><ul class="archml-type-children"><li>${inner}</li></ul>`;
    }

    case "map": {
      const k = renderTypeRef(type.key_type, files, visited);
      const v = renderTypeRef(type.value_type, files, visited);
      return `<span class="archml-type-wrapper">Map</span><ul class="archml-type-children"><li><span class="archml-type-role">key </span>${k}</li><li><span class="archml-type-role">val </span>${v}</li></ul>`;
    }

    case "named": {
      const nameHtml = `<span class="archml-type-named">${escText(type.name)}</span>`;
      if (visited.has(type.name)) return nameHtml + `<span class="archml-type-recursive"> …</span>`;
      const def = findTypeDef(files, type.name);
      if (!def || def.fields.length === 0) return nameHtml;
      const next = new Set(visited).add(type.name);
      const fieldsHtml = def.fields
        .map((f) => `<li class="archml-type-field"><span class="archml-type-fname">${escText(f.name)}</span><span class="archml-type-sep">:</span>${renderTypeRef(f.type, files, next)}</li>`)
        .join("");
      return `${nameHtml}<ul class="archml-type-children">${fieldsHtml}</ul>`;
    }
  }
}

function escText(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
