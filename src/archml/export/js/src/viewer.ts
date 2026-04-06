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
import "highlight.js/styles/github.css";
import hljs from "highlight.js/lib/core";
import hljsBash from "highlight.js/lib/languages/bash";
import hljsC from "highlight.js/lib/languages/c";
import hljsCpp from "highlight.js/lib/languages/cpp";
import hljsCss from "highlight.js/lib/languages/css";
import hljsGo from "highlight.js/lib/languages/go";
import hljsJava from "highlight.js/lib/languages/java";
import hljsJs from "highlight.js/lib/languages/javascript";
import hljsJson from "highlight.js/lib/languages/json";
import hljsKotlin from "highlight.js/lib/languages/kotlin";
import hljsMarkdown from "highlight.js/lib/languages/markdown";
import hljsPython from "highlight.js/lib/languages/python";
import hljsRust from "highlight.js/lib/languages/rust";
import hljsScala from "highlight.js/lib/languages/scala";
import hljsShell from "highlight.js/lib/languages/shell";
import hljsSql from "highlight.js/lib/languages/sql";
import hljsTs from "highlight.js/lib/languages/typescript";
import hljsXml from "highlight.js/lib/languages/xml";
import hljsYaml from "highlight.js/lib/languages/yaml";

hljs.registerLanguage("bash", hljsBash);
hljs.registerLanguage("c", hljsC);
hljs.registerLanguage("cpp", hljsCpp);
hljs.registerLanguage("css", hljsCss);
hljs.registerLanguage("go", hljsGo);
hljs.registerLanguage("java", hljsJava);
hljs.registerLanguage("javascript", hljsJs);
hljs.registerLanguage("js", hljsJs);
hljs.registerLanguage("json", hljsJson);
hljs.registerLanguage("kotlin", hljsKotlin);
hljs.registerLanguage("markdown", hljsMarkdown);
hljs.registerLanguage("python", hljsPython);
hljs.registerLanguage("py", hljsPython);
hljs.registerLanguage("rust", hljsRust);
hljs.registerLanguage("scala", hljsScala);
hljs.registerLanguage("shell", hljsShell);
hljs.registerLanguage("sh", hljsBash);
hljs.registerLanguage("sql", hljsSql);
hljs.registerLanguage("typescript", hljsTs);
hljs.registerLanguage("ts", hljsTs);
hljs.registerLanguage("xml", hljsXml);
hljs.registerLanguage("html", hljsXml);
hljs.registerLanguage("yaml", hljsYaml);
hljs.registerLanguage("yml", hljsYaml);

// ─── Public API ───────────────────────────────────────────────────────────────

/** Mount the full interactive viewer into *container*. */
export function mountViewer(container: HTMLElement, payload: ViewerPayload): void {
  container.innerHTML = buildViewerShell();
  container.className = "archml-viewer";

  const canvasArea = container.querySelector<HTMLElement>(".archml-canvas-area")!;
  const canvasTransform = container.querySelector<HTMLElement>(".archml-canvas-transform")!;
  const detailsSidebar = container.querySelector<HTMLElement>(".archml-sidebar-right-body")!;
  const entitySelectWrap = container.querySelector<HTMLElement>("#archml-entity-select-wrap")!;
  const depthSelect = container.querySelector<HTMLSelectElement>("#archml-depth-select")!;
  const variantSelect = container.querySelector<HTMLSelectElement>("#archml-variant-select")!;
  const errorBanner = container.querySelector<HTMLElement>(".archml-error-banner")!;
  const loadingEl = container.querySelector<HTMLElement>(".archml-loading")!;

  // Expand/collapse toggle for right sidebar
  const expandBtn = container.querySelector<HTMLElement>("#archml-sidebar-expand-btn");
  const rightSidebar = container.querySelector<HTMLElement>(".archml-sidebar-right");
  expandBtn?.addEventListener("click", () => {
    const expanded = rightSidebar!.classList.toggle("archml-sidebar-right--expanded");
    const svg = expandBtn.querySelector("svg");
    if (svg) {
      svg.innerHTML = expanded
        ? `<polyline points="5,1 1,1 1,5"/><polyline points="11,1 15,1 15,5"/><polyline points="15,11 15,15 11,15"/><polyline points="5,15 1,15 1,11"/><line x1="1" y1="1" x2="6" y2="6"/><line x1="15" y1="1" x2="10" y2="6"/><line x1="15" y1="15" x2="10" y2="10"/><line x1="1" y1="15" x2="6" y2="10"/>`
        : `<polyline points="1,5 1,1 5,1"/><polyline points="11,1 15,1 15,5"/><polyline points="15,11 15,15 11,15"/><polyline points="5,15 1,15 1,11"/>`;
    }
    expandBtn.title = expanded ? "Collapse sidebar" : "Expand sidebar";
  });

  // Populate variant dropdown (named variants shown in italic)
  const allVariants = collectAllVariants(payload.files);
  for (const v of allVariants) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    opt.style.fontStyle = "italic";
    variantSelect.appendChild(opt);
  }

  // Build custom entity dropdown (initially showing all variants)
  const initialEntities = filterEntitiesByVariant(payload.entities, payload.files, variantSelect.value);
  const customEntitySelect = buildCustomEntitySelect(entitySelectWrap, initialEntities, () => {
    void renderDiagram();
  });

  // Variant change → re-filter entity list and re-render
  variantSelect.addEventListener("change", () => {
    const filtered = filterEntitiesByVariant(payload.entities, payload.files, variantSelect.value);
    customEntitySelect.setEntities(filtered);
    void renderDiagram();
  });

  // Pan/zoom state
  let tx = 0, ty = 0, scale = 1.0;
  let dragging = false, startX = 0, startY = 0, didDrag = false;

  function applyTransform(): void {
    canvasTransform.style.transform = `translate(${tx}px,${ty}px) scale(${scale})`;
  }

  function fitTransform(): void {
    const svgEl = canvasTransform.querySelector("svg");
    if (!svgEl) { tx = 0; ty = 0; scale = 1.0; applyTransform(); return; }
    const svgW = svgEl.getAttribute("width") ? parseFloat(svgEl.getAttribute("width")!) : svgEl.viewBox.baseVal.width;
    const svgH = svgEl.getAttribute("height") ? parseFloat(svgEl.getAttribute("height")!) : svgEl.viewBox.baseVal.height;
    if (!svgW || !svgH) { tx = 0; ty = 0; scale = 1.0; applyTransform(); return; }
    const { width: cw, height: ch } = canvasArea.getBoundingClientRect();
    const padding = 32;
    scale = Math.min((cw - padding * 2) / svgW, (ch - padding * 2) / svgH, 1.5);
    tx = (cw - svgW * scale) / 2;
    ty = (ch - svgH * scale) / 2;
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

    const variantFilter = variantSelect.value;

    try {
      let diagram: VizDiagram;
      if (entityValue === "all") {
        currentEntity = null;
        diagram = buildVizDiagramAll(payload.files, depth, variantFilter);
      } else {
        const entity = findEntity(payload.files, entityValue);
        if (!entity) {
          errorBanner.textContent = `Entity not found: ${entityValue}`;
          errorBanner.style.display = "block";
          loadingEl.style.display = "none";
          return;
        }
        currentEntity = entity;
        diagram = buildVizDiagram(entity, depth, collectParentConnects(payload.files, entity), variantFilter);
      }

      const plan: LayoutPlan = await computeLayout(diagram);
      const svg = renderToSvgString(diagram, plan);
      canvasTransform.innerHTML = svg;
      fitTransform();
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

function buildViewerShell(): string {
  return `
    <div class="archml-topbar">
      <span class="archml-topbar-title">ArchML Explorer</span>
    </div>
    <div class="archml-body">
      <div class="archml-sidebar-left">
        <div>
          <label for="archml-variant-select">Variant</label>
          <select id="archml-variant-select">
            <option value="*">All Variants</option>
            <option value="">Baseline</option>
          </select>
        </div>
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
        <div class="archml-sidebar-right-header">
          <span class="archml-sidebar-right-title">Details</span>
          <button class="archml-sidebar-expand-btn" id="archml-sidebar-expand-btn" type="button" title="Expand sidebar">
            <svg class="archml-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="1,5 1,1 5,1"/><polyline points="11,1 15,1 15,5"/>
              <polyline points="15,11 15,15 11,15"/><polyline points="5,15 1,15 1,11"/>
            </svg>
          </button>
        </div>
        <div class="archml-sidebar-right-body">
          <p class="archml-detail-empty">Click an entity to see details.</p>
        </div>
      </div>
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
  initialEntities: EntityEntry[],
  onChange: () => void,
): { getValue: () => string; setEntities: (entities: EntityEntry[]) => void } {
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

  function buildPanel(entities: EntityEntry[]): void {
    panel.innerHTML = "";
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

    // If the selected entity is no longer in the filtered list, reset to "all"
    if (currentValue !== "all" && !entities.some((e) => e.qualified_name === currentValue)) {
      currentValue = "all";
      setTriggerContent("All entities", null);
    }
  }

  buildPanel(initialEntities);
  setTriggerContent("All entities", null);

  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    isOpen = !isOpen;
    panel.hidden = !isOpen;
    trigger.classList.toggle("is-open", isOpen);
  });

  document.addEventListener("click", () => { if (isOpen) close(); });

  return {
    getValue: () => currentValue,
    setEntities: (entities: EntityEntry[]) => { buildPanel(entities); },
  };
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
  const name = entityPath.split("::").pop() ?? entityPath;
  const description = entity?.description ?? null;
  const requires = entity?.requires ?? [];
  const provides = entity?.provides ?? [];
  const kindLabel = entityKind.replace(/_/g, " ");

  const variants: string[] = entity?.variants ?? [];

  let html = `
    <h3 class="archml-detail-title">${escText(name)}</h3>
    <div class="archml-detail-kind">${escText(kindLabel)}</div>
  `;

  if (description) {
    html += detailsSection("Description", `<div class="archml-detail-description">${renderMarkdown(description)}</div>`);
  }

  {
    const variantBody = variants.length > 0
      ? variants.map((v) => `<span class="archml-detail-pill">${escText(v)}</span>`).join("")
      : `<span class="archml-detail-muted">baseline — present in all variants</span>`;
    html += detailsSection("Variants", variantBody, false);
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
    <h3 class="archml-detail-title">${escText(def.name)}</h3>
    <div class="archml-detail-kind">interface</div>
  `;

  if (def.description) {
    html += detailsSection("Description", `<div class="archml-detail-description">${renderMarkdown(def.description)}</div>`);
  }

  {
    const ifaceVariants: string[] = def.variants ?? [];
    const variantBody = ifaceVariants.length > 0
      ? ifaceVariants.map((v) => `<span class="archml-detail-pill">${escText(v)}</span>`).join("")
      : `<span class="archml-detail-muted">baseline — present in all variants</span>`;
    html += detailsSection("Variants", variantBody, false);
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

// ─── Variant helpers ──────────────────────────────────────────────────────────

function collectAllVariants(files: Record<string, ArchFileJson>): string[] {
  const variants = new Set<string>();
  for (const af of Object.values(files)) {
    for (const sys of af.systems) _collectVariantsFromSystem(sys, variants);
    for (const comp of af.components) _collectVariantsFromComponent(comp, variants);
  }
  return [...variants].sort();
}

function _collectVariantsFromSystem(sys: SystemJson, variants: Set<string>): void {
  for (const v of sys.variants ?? []) variants.add(v);
  for (const sub of sys.systems) _collectVariantsFromSystem(sub, variants);
  for (const comp of sys.components) _collectVariantsFromComponent(comp, variants);
}

function _collectVariantsFromComponent(comp: ComponentJson, variants: Set<string>): void {
  for (const v of comp.variants ?? []) variants.add(v);
  for (const sub of comp.components) _collectVariantsFromComponent(sub, variants);
}

function filterEntitiesByVariant(
  entities: EntityEntry[],
  files: Record<string, ArchFileJson>,
  variantFilter: string,
): EntityEntry[] {
  if (variantFilter === "*") return entities;
  return entities.filter((e) => {
    const entity = findEntity(files, e.qualified_name);
    if (!entity) return true;
    const evars = entity.variants ?? [];
    if (variantFilter === "") return evars.length === 0;
    return evars.length === 0 || evars.includes(variantFilter);
  });
}

// ─── Markdown renderer ────────────────────────────────────────────────────────

/**
 * Convert a Markdown string to safe HTML. Handles headings (#–###), fenced
 * code blocks (``` or ~~~), paragraphs, bold, italic, inline code, and
 * https/http links. Processes line-by-line so headings don't need blank-line
 * separation. All user content is HTML-escaped before expansion.
 */
function renderMarkdown(md: string): string {
  // Dedent: find the minimum indentation of non-blank lines and strip it.
  const rawLines = md.split("\n");
  const minIndent = rawLines
    .filter((l) => l.trim().length > 0)
    .reduce((min, l) => Math.min(min, l.match(/^(\s*)/)?.[1].length ?? 0), Infinity);
  const indent = isFinite(minIndent) ? minIndent : 0;
  const lines = rawLines.map((l) => l.slice(indent));

  const out: string[] = [];
  let paraLines: string[] = [];
  let inFence = false;
  let fenceLang = "";
  let fenceLines: string[] = [];

  function flushPara(): void {
    if (paraLines.length === 0) return;
    out.push(`<p>${_renderInline(paraLines.join(" "))}</p>`);
    paraLines = [];
  }

  for (const line of lines) {
    const trimmed = line.trim();

    // Fenced code block toggle (``` or ~~~)
    if (trimmed.startsWith("```") || trimmed.startsWith("~~~")) {
      if (!inFence) {
        flushPara();
        inFence = true;
        fenceLang = trimmed.slice(3).trim().toLowerCase();
        fenceLines = [];
      } else {
        // Dedent code lines by their own common indent.
        const codeIndent = fenceLines
          .filter((l) => l.trim().length > 0)
          .reduce((min, l) => Math.min(min, l.match(/^(\s*)/)?.[1].length ?? 0), Infinity);
        const ci = isFinite(codeIndent) ? codeIndent : 0;
        const dedented = fenceLines.map((l) => l.slice(ci)).join("\n");

        let highlighted: string;
        if (fenceLang && hljs.getLanguage(fenceLang)) {
          highlighted = hljs.highlight(dedented, { language: fenceLang }).value;
        } else {
          highlighted = dedented.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }
        const langAttr = fenceLang ? ` class="language-${fenceLang}"` : "";
        out.push(`<pre class="archml-md-pre"><code${langAttr}>${highlighted}</code></pre>`);
        inFence = false;
        fenceLang = "";
        fenceLines = [];
      }
      continue;
    }
    if (inFence) {
      fenceLines.push(line);
      continue;
    }

    // Headings
    const hm = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (hm) {
      flushPara();
      const level = hm[1].length;
      out.push(`<h${level} class="archml-md-h${level}">${_renderInline(hm[2])}</h${level}>`);
      continue;
    }

    // Blank line → flush paragraph
    if (trimmed === "") {
      flushPara();
      continue;
    }

    paraLines.push(trimmed);
  }

  flushPara();
  return out.join("\n");
}

function _renderInline(text: string): string {
  // 1. Escape HTML special characters.
  let s = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  // 2. Extract code spans before other transformations to prevent inner parsing.
  const codeSpans: string[] = [];
  s = s.replace(/`([^`]+)`/g, (_, code) => {
    const idx = codeSpans.length;
    codeSpans.push(`<code>${code}</code>`); // code content already html-escaped above
    return `\x00CODE${idx}\x00`;
  });

  // 3. Bold: **text**
  s = s.replace(/\*\*([^*]+)\*\*/g, (_, t) => `<strong>${t}</strong>`);

  // 4. Italic: *text* (only single asterisks remaining after step 3)
  s = s.replace(/\*([^*]+)\*/g, (_, t) => `<em>${t}</em>`);

  // 5. Links: [text](url) — only http/https URLs are allowed.
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, linkText, url) => {
    const rawUrl = url.trim();
    const safeUrl = /^https?:\/\//i.test(rawUrl) ? rawUrl.replace(/"/g, "&quot;") : "#";
    return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${linkText}</a>`;
  });

  // 6. Restore code spans.
  s = s.replace(/\x00CODE(\d+)\x00/g, (_, idx) => codeSpans[parseInt(idx, 10)]);

  return s;
}
