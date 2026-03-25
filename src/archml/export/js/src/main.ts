// Copyright 2026 ArchML Contributors
// SPDX-License-Identifier: Apache-2.0

// Entry point for both the standalone HTML export and the Sphinx JS asset.
//
// Standalone HTML (archml export):
//   Reads payload from <script id="archml-data" type="application/json">
//   and mounts the full interactive viewer into <div id="archml-app">.
//
// Sphinx HTML embed:
//   Scans for .archml-embed elements, reads their data-entity / data-depth
//   attributes plus the nearest <script type="application/json" class="archml-embed-data">
//   sibling and mounts a fixed-entity pan/zoom viewer.

import "./archml-diagram.css";
import type { ViewerPayload } from "./types";
import { mountViewer, mountEmbed } from "./viewer";

function readPayload(scriptEl: HTMLScriptElement | null): ViewerPayload | null {
  if (!scriptEl) return null;
  try {
    return JSON.parse(scriptEl.textContent ?? "") as ViewerPayload;
  } catch {
    console.error("[archml] Failed to parse viewer payload JSON");
    return null;
  }
}

function initStandalone(): void {
  const dataScript = document.getElementById("archml-data") as HTMLScriptElement | null;
  const payload = readPayload(dataScript);
  const appEl = document.getElementById("archml-app");
  if (!payload || !appEl) return;
  mountViewer(appEl, payload);
}

function initEmbeds(): void {
  // Sphinx embeds: <div class="archml-embed" data-entity="X" data-depth="2">
  //                  <script type="application/json" class="archml-embed-data">...</script>
  //                </div>
  const embeds = document.querySelectorAll<HTMLElement>(".archml-embed[data-entity]");
  embeds.forEach((el) => {
    const entityPath = el.dataset["entity"] ?? "all";
    const depthStr = el.dataset["depth"] ?? "full";
    const depth = depthStr === "full" ? null : parseInt(depthStr, 10);

    const dataScript = el.querySelector<HTMLScriptElement>('script[type="application/json"]');
    const payload = readPayload(dataScript);
    if (!payload) {
      el.textContent = "[archml] Missing data payload";
      return;
    }
    mountEmbed(el, payload, entityPath, depth);
  });
}

function init(): void {
  // Standalone mode: <div id="archml-app"> exists
  if (document.getElementById("archml-app")) {
    initStandalone();
  }
  // Sphinx embed mode: .archml-embed elements exist
  initEmbeds();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
