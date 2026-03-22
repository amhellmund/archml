// Copyright 2026 ArchML Contributors
// SPDX-License-Identifier: Apache-2.0

// Interactive diagram support: pan/zoom and entity selection.
// Loaded automatically by Dash from the assets/ directory.

(function () {
    "use strict";

    var state = { tx: 0, ty: 0, scale: 1.0, dragging: false, sx: 0, sy: 0, didDrag: false };

    function getContainer() { return document.getElementById("svg-viewport-container"); }
    function getContent() { return document.getElementById("svg-transform-container"); }

    function applyTransform() {
        var c = getContent();
        if (c) {
            c.style.transform = "translate(" + state.tx + "px," + state.ty + "px) scale(" + state.scale + ")";
            c.style.transformOrigin = "0 0";
        }
    }

    function resetTransform() {
        state.tx = 0; state.ty = 0; state.scale = 1.0;
        applyTransform();
    }

    function onMouseDown(e) {
        if (e.button !== 0) return;
        state.dragging = true;
        state.didDrag = false;
        state.sx = e.clientX - state.tx;
        state.sy = e.clientY - state.ty;
        var c = getContainer();
        if (c) c.style.cursor = "grabbing";
        e.preventDefault();
    }

    function onMouseMove(e) {
        if (!state.dragging) return;
        state.didDrag = true;
        state.tx = e.clientX - state.sx;
        state.ty = e.clientY - state.sy;
        applyTransform();
    }

    function onMouseUp() {
        state.dragging = false;
        var c = getContainer();
        if (c) c.style.cursor = "grab";
    }

    function onWheel(e) {
        e.preventDefault();
        var container = getContainer();
        if (!container) return;
        var rect = container.getBoundingClientRect();
        var mx = e.clientX - rect.left;
        var my = e.clientY - rect.top;
        var factor = e.deltaY > 0 ? 0.9 : 1.1;
        var newScale = Math.max(0.05, Math.min(20.0, state.scale * factor));
        state.tx = mx - (mx - state.tx) * (newScale / state.scale);
        state.ty = my - (my - state.ty) * (newScale / state.scale);
        state.scale = newScale;
        applyTransform();
    }

    function onEntityClick(e) {
        if (state.didDrag) {
            state.didDrag = false;
            return;
        }
        var t = e.target.closest(".archml-entity");
        if (t) {
            window._archmlClicked = {
                entity_path: t.getAttribute("data-entity-path") || "",
                kind: t.getAttribute("data-entity-kind") || ""
            };
        } else {
            window._archmlClicked = null;
        }
    }

    var _initialized = false;

    function init() {
        var container = getContainer();
        if (!container || _initialized) return;
        _initialized = true;

        container.style.cursor = "grab";

        container.addEventListener("mousedown", onMouseDown);
        document.addEventListener("mousemove", onMouseMove);
        document.addEventListener("mouseup", onMouseUp);
        container.addEventListener("wheel", onWheel, { passive: false });
        container.addEventListener("click", onEntityClick, { capture: true });

        applyTransform();
    }

    function tryInit() {
        init();
        if (!_initialized) {
            var obs = new MutationObserver(function (_, observer) {
                if (getContainer()) {
                    init();
                    if (_initialized) observer.disconnect();
                }
            });
            obs.observe(document.body, { childList: true, subtree: true });
        }
    }

    // Expose state and reset function for Dash clientside callbacks.
    window._archmlState = state;
    window.archmlResetTransform = resetTransform;

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", tryInit);
    } else {
        tryInit();
    }
})();
