# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Dash-based web UI for interactive architecture viewing."""

from __future__ import annotations

from pathlib import Path

import dash
import dash_mantine_components as dmc
from dash import Input, Output, clientside_callback, dcc, html

from archml.compiler.build import CompilerError, SourceImportKey, compile_files
from archml.model.entities import ArchFile, Component, InterfaceDef, System, UserDef
from archml.model.types import (
    ListTypeRef,
    MapTypeRef,
    NamedTypeRef,
    OptionalTypeRef,
    PrimitiveTypeRef,
    TypeRef,
)
from archml.views.diagram import render_diagram_to_svg_string
from archml.views.layout import compute_layout
from archml.views.resolver import EntityNotFoundError, resolve_entity
from archml.views.topology import build_viz_diagram, build_viz_diagram_all
from archml.workspace.config import LocalPathImport, WorkspaceConfigError, load_workspace_config

# ###############
# Public Interface
# ###############

_DEPTH_OPTIONS = [
    {"label": "Full depth", "value": "full"},
    {"label": "0 - root only", "value": "0"},
    {"label": "1 - children", "value": "1"},
    {"label": "2 - grand children", "value": "2"},
]


def create_app(directory: Path) -> dash.Dash:
    """Create and configure the ArchML web UI application."""
    arch_files, compile_error = _compile_workspace(directory)

    app = dash.Dash(
        __name__,
        title="ArchML Architecture Viewer",
        suppress_callback_exceptions=True,
    )

    entity_options = _build_entity_options(arch_files)
    app.layout = dmc.MantineProvider(
        _build_layout(entity_options, compile_error),
        theme={"colorScheme": "light"},
        forceColorScheme="light",
    )

    _register_callbacks(app, arch_files)
    return app


# ################
# Implementation
# ################


def _compile_workspace(directory: Path) -> tuple[dict[str, ArchFile], str]:
    """Compile the workspace and return (arch_files, error_message)."""
    workspace_yaml = directory / ".archml-workspace.yaml"
    if not workspace_yaml.exists():
        return {}, f"No workspace found at '{directory}'. Run 'archml init' first."

    try:
        config = load_workspace_config(workspace_yaml)
    except WorkspaceConfigError as exc:
        return {}, f"Workspace config error: {exc}"

    build_dir = directory / config.build_directory
    source_import_map: dict[SourceImportKey, Path] = {}
    for imp in config.source_imports:
        if isinstance(imp, LocalPathImport):
            source_import_map[SourceImportKey(config.name, imp.name)] = (directory / imp.local_path).resolve()

    archml_files = [f for f in directory.rglob("*.archml") if build_dir not in f.parents]
    if not archml_files:
        return {}, "No .archml files found in the workspace."

    try:
        compiled = compile_files(archml_files, build_dir, source_import_map)
    except CompilerError as exc:
        return {}, f"Compiler error: {exc}"

    return compiled, ""


def _build_entity_options(arch_files: dict[str, ArchFile]) -> list[dict]:
    """Build the entity select options from compiled arch files."""
    options: list[dict] = [{"label": "All entities", "value": "all"}]
    systems_items: list[dict] = []
    components_items: list[dict] = []

    seen: set[str] = set()

    def _collect(entity: Component | System, prefix: str = "") -> None:
        path = f"{prefix}{entity.name}" if not prefix else f"{prefix}::{entity.name}"
        qname = entity.qualified_name or path
        if qname in seen:
            return
        seen.add(qname)
        if isinstance(entity, System):
            systems_items.append({"label": f"🔵 {entity.name}", "value": qname})
            for sub in entity.systems:
                _collect(sub, qname)
            for comp in entity.components:
                _collect(comp, qname)
        else:
            components_items.append({"label": f"🟠 {entity.name}", "value": qname})
            for comp in entity.components:
                _collect(comp, qname)

    for af in arch_files.values():
        for sys in af.systems:
            _collect(sys)
        for comp in af.components:
            _collect(comp)

    if systems_items:
        options.append({"group": "Systems", "items": systems_items})
    if components_items:
        options.append({"group": "Components", "items": components_items})

    return options


def _build_layout(entity_options: list[dict], compile_error: str) -> dmc.AppShell:
    """Build the 3-pane application layout."""
    return dmc.AppShell(
        [
            dmc.AppShellNavbar(
                _build_left_sidebar(entity_options, compile_error),
                withBorder=True,
                p="sm",
            ),
            dmc.AppShellMain(
                _build_canvas_pane(),
                style={"padding": 0, "overflow": "hidden"},
            ),
            dmc.AppShellAside(
                _build_right_sidebar(),
                withBorder=True,
                p="sm",
            ),
        ],
        navbar={"width": 260, "breakpoint": "sm"},
        aside={"width": 320, "breakpoint": "sm"},
        padding=0,
    )


def _build_left_sidebar(entity_options: list[dict], compile_error: str) -> list:
    """Build the left navigation sidebar contents."""
    error_section = []
    if compile_error:
        error_section = [
            dmc.Alert(
                compile_error,
                color="red",
                title="Load error",
                mb="md",
            )
        ]

    return [
        dmc.Title("ArchML Viewer", order=4, mb="md"),
        *error_section,
        dmc.Text("Element", size="sm", fw=500, mb=4),
        dmc.Select(
            id="entity-select",
            data=entity_options,
            value="all",
            searchable=True,
            allowDeselect=False,
            mb="md",
        ),
        dmc.Text("Depth", size="sm", fw=500, mb=4),
        dmc.Select(
            id="depth-select",
            data=_DEPTH_OPTIONS,
            value="full",
            allowDeselect=False,
            mb="md",
        ),
        dmc.Divider(mb="md"),
        dmc.Text(
            f"{len(entity_options) - 1} entities loaded" if entity_options else "No entities",
            size="xs",
            c="dimmed",
        ),
        # Hidden stores and dummy outputs
        dcc.Store(id="selected-entity-store", data=None),
        html.Div(id="reset-transform-dummy", style={"display": "none"}),
    ]


def _build_canvas_pane() -> html.Div:
    """Build the main SVG canvas with pan/zoom container."""
    return html.Div(
        id="svg-viewport-container",
        n_clicks=0,
        style={
            "width": "100%",
            "height": "100vh",
            "overflow": "hidden",
            "background": "#f8fafc",
            "cursor": "grab",
            "position": "relative",
        },
        children=[
            html.Div(
                id="svg-transform-container",
                style={"transformOrigin": "0 0", "display": "inline-block"},
                children=[
                    dcc.Markdown(
                        id="svg-markdown",
                        dangerously_allow_html=True,
                        children="",
                        style={"margin": 0, "padding": 0},
                    )
                ],
            ),
            html.Div(
                id="diagram-error-banner",
                style={
                    "position": "absolute",
                    "top": "50%",
                    "left": "50%",
                    "transform": "translate(-50%, -50%)",
                    "color": "#dc2626",
                    "fontFamily": "system-ui, sans-serif",
                    "textAlign": "center",
                    "pointerEvents": "none",
                },
            ),
        ],
    )


def _build_right_sidebar() -> list:
    """Build the right details sidebar initial contents."""
    return [
        dmc.Title("Details", order=4, mb="md"),
        html.Div(
            id="entity-details",
            children=[
                dmc.Text("Click an element to see its details.", size="sm", c="dimmed"),
            ],
        ),
    ]


def _register_callbacks(app: dash.Dash, arch_files: dict[str, ArchFile]) -> None:
    """Register all Dash callbacks."""

    # --- Diagram rendering ---
    @app.callback(
        Output("svg-markdown", "children"),
        Output("diagram-error-banner", "children"),
        Input("entity-select", "value"),
        Input("depth-select", "value"),
    )
    def update_diagram(entity_value: str | None, depth_value: str | None) -> tuple:
        if not arch_files:
            return "", "No architecture files loaded."

        entity_value = entity_value or "all"
        depth: int | None = None if depth_value == "full" else int(depth_value or "full")

        try:
            if entity_value == "all":
                diagram = build_viz_diagram_all(arch_files, depth=depth)
            else:
                entity = _lookup_entity(arch_files, entity_value)
                if entity is None:
                    return "", f"Entity not found: '{entity_value}'"
                if isinstance(entity, UserDef):
                    return "", f"Cannot visualize user entity '{entity_value}' as a diagram."
                global_connects = [c for af in arch_files.values() for c in af.connects]
                diagram = build_viz_diagram(entity, depth=depth, global_connects=global_connects)

            plan = compute_layout(diagram)
            svg_string = render_diagram_to_svg_string(diagram, plan)
        except RuntimeError as exc:
            return "", f"Layout error: {exc}"
        except Exception as exc:  # noqa: BLE001
            return "", f"Error rendering diagram: {exc}"

        return svg_string, ""

    # --- Reset pan/zoom when SVG changes ---
    clientside_callback(
        """
        function(children) {
            if (window.archmlResetTransform) {
                setTimeout(window.archmlResetTransform, 50);
            }
            return "";
        }
        """,
        Output("reset-transform-dummy", "children"),
        Input("svg-markdown", "children"),
        prevent_initial_call=True,
    )

    # --- Entity selection via SVG click ---
    clientside_callback(
        """
        function(n_clicks) {
            if (!n_clicks) return window.dash_clientside.no_update;
            if (window._archmlState && window._archmlState.didDrag) return window.dash_clientside.no_update;
            var clicked = window._archmlClicked;
            if (clicked && clicked.entity_path) return clicked;
            return null;
        }
        """,
        Output("selected-entity-store", "data"),
        Input("svg-viewport-container", "n_clicks"),
        prevent_initial_call=True,
    )

    # --- Right sidebar details ---
    @app.callback(
        Output("entity-details", "children"),
        Input("selected-entity-store", "data"),
    )
    def update_details(selected: dict | None):
        if not selected or not selected.get("entity_path"):
            return dmc.Text("Click an element to see its details.", size="sm", c="dimmed")

        entity_path: str = selected["entity_path"]
        kind: str = selected.get("kind", "")

        # Interface terminal or channel — entity_path holds the interface name.
        if kind in ("terminal", "interface", "channel"):
            channel: str | None = selected.get("channel") or None
            iface = _find_interface_def(arch_files, entity_path)
            if iface:
                return _render_interface_details(iface, channel=channel)
            return dmc.Text(f"Interface '{entity_path}' not found.", size="sm", c="dimmed")

        # Component / System / User → look up by qualified_name
        entity = _lookup_entity(arch_files, entity_path)
        if entity is None:
            return dmc.Text(f"Entity '{entity_path}' not found.", size="sm", c="dimmed")

        return _render_entity_details(entity, kind)


def _render_entity_details(entity: Component | System | UserDef, kind: str) -> list:
    """Render the right sidebar content for a component, system, or user entity."""
    color_map = {
        "component": "orange",
        "system": "blue",
        "user": "yellow",
        "external_component": "gray",
        "external_system": "gray",
        "external_user": "gray",
    }
    badge_color = color_map.get(kind, "gray")

    items: list = [
        dmc.Group(
            [
                dmc.Title(entity.title or entity.name, order=5, style={"flex": 1}),
                dmc.Badge(kind.replace("_", " "), color=badge_color, size="sm"),
            ],
            align="center",
            mb="xs",
        ),
    ]

    if entity.title and entity.title != entity.name:
        items.append(dmc.Text(f"({entity.name})", size="xs", c="dimmed", mb="xs"))

    if entity.description:
        items.append(dmc.Text(entity.description, size="sm", mb="sm"))

    if entity.tags:
        items.append(
            dmc.Group(
                [dmc.Badge(tag, size="xs", variant="outline") for tag in entity.tags],
                gap=4,
                mb="sm",
            )
        )

    if isinstance(entity, (Component, System)) and entity.is_external:
        items.append(dmc.Badge("external", size="xs", color="gray", variant="dot", mb="xs"))

    # Requires / Provides
    if hasattr(entity, "requires") and entity.requires:
        items.append(dmc.Divider(label="Requires", labelPosition="left", my="xs"))
        for ref in entity.requires:
            label = ref.name + (f" @{ref.version}" if ref.version else "")
            items.append(dmc.Text(f"• {label}", size="sm", style={"fontFamily": "monospace"}))

    if hasattr(entity, "provides") and entity.provides:
        items.append(dmc.Divider(label="Provides", labelPosition="left", my="xs"))
        for ref in entity.provides:
            label = ref.name + (f" @{ref.version}" if ref.version else "")
            items.append(dmc.Text(f"• {label}", size="sm", style={"fontFamily": "monospace"}))

    return items


def _render_interface_details(iface: InterfaceDef, *, channel: str | None = None) -> list:
    """Render the right sidebar content for an interface definition."""
    heading = iface.name + (f" @{iface.version}" if iface.version else "")

    items: list = [
        dmc.Group(
            [
                dmc.Title(iface.title or heading, order=5, style={"flex": 1}),
                dmc.Badge("interface", color="red", size="sm"),
            ],
            align="center",
            mb="xs",
        ),
    ]

    if iface.title and iface.title != iface.name:
        items.append(dmc.Text(f"({heading})", size="xs", c="dimmed", mb="xs"))

    if iface.description:
        items.append(dmc.Text(iface.description, size="sm", mb="sm"))

    if iface.tags:
        items.append(
            dmc.Group(
                [dmc.Badge(tag, size="xs", variant="outline") for tag in iface.tags],
                gap=4,
                mb="sm",
            )
        )

    if iface.fields:
        items.append(dmc.Divider(label="Fields", labelPosition="left", my="xs"))
        for field in iface.fields:
            type_str = _format_type_ref(field.type)
            items.append(
                dmc.Group(
                    [
                        dmc.Text(field.name, size="sm", fw=500, style={"fontFamily": "monospace", "flex": 1}),
                        dmc.Text(type_str, size="xs", c="dimmed", style={"fontFamily": "monospace"}),
                    ],
                    justify="space-between",
                    mb=2,
                )
            )
            if field.description:
                items.append(dmc.Text(field.description, size="xs", c="dimmed", mb=4, ml="md"))

    if channel:
        items.append(dmc.Divider(label="Channels", labelPosition="left", my="xs"))
        items.append(dmc.Text(f"${channel}", size="sm", style={"fontFamily": "monospace"}))

    return items


def _lookup_entity(
    arch_files: dict[str, ArchFile],
    path: str,
) -> Component | System | UserDef | None:
    """Find an entity by its full ``qualified_name`` or bare name-based path.

    The topology stores ``entity.qualified_name`` (which includes the file-key
    prefix, e.g. ``"testrepo/system::Order::B"``).  ``resolve_entity`` only
    understands bare name paths (``"Order::B"``).  This function searches by
    ``qualified_name`` first, then falls back to ``resolve_entity``.
    """
    # Search all entities recursively by qualified_name.
    for af in arch_files.values():
        for sys in af.systems:
            hit = _match_by_qname(sys, path)
            if hit is not None:
                return hit
        for comp in af.components:
            hit = _match_by_qname(comp, path)
            if hit is not None:
                return hit
        for user in af.users:
            if user.qualified_name == path or user.name == path:
                return user
    # Fallback: treat path as a bare name-based path for resolve_entity.
    try:
        return resolve_entity(arch_files, path)
    except EntityNotFoundError:
        return None


def _match_by_qname(
    entity: Component | System,
    path: str,
) -> Component | System | None:
    """Recursively search *entity* and its descendants for a qualified_name match."""
    if entity.qualified_name == path or entity.name == path:
        return entity
    if isinstance(entity, System):
        for sub in entity.systems:
            hit = _match_by_qname(sub, path)
            if hit is not None:
                return hit
    for comp in entity.components:
        hit = _match_by_qname(comp, path)
        if hit is not None:
            return hit
    return None


def _find_interface_def(arch_files: dict[str, ArchFile], name: str) -> InterfaceDef | None:
    """Search all arch files for an InterfaceDef with the given name.

    *name* may be a bare interface name (``"OrderRequest"``) or a versioned
    label produced by the topology (``"OrderRequest@1.0"``).  Both forms are
    handled so that clicking a terminal node always resolves correctly.

    Searches top-level file interfaces first, then interfaces nested inside
    components and systems (e.g. ``interface AInternal`` inside ``component A``).
    """
    bare_name, _, version = name.partition("@")

    def _match(iface: InterfaceDef) -> bool:
        return iface.name == bare_name and (not version or iface.version == version)

    def _search_component(comp: Component) -> InterfaceDef | None:
        for iface in comp.interfaces:
            if _match(iface):
                return iface
        for sub in comp.components:
            hit = _search_component(sub)
            if hit is not None:
                return hit
        return None

    def _search_system(sys: System) -> InterfaceDef | None:
        for iface in sys.interfaces:
            if _match(iface):
                return iface
        for comp in sys.components:
            hit = _search_component(comp)
            if hit is not None:
                return hit
        for sub in sys.systems:
            hit = _search_system(sub)
            if hit is not None:
                return hit
        return None

    for af in arch_files.values():
        for iface in af.interfaces:
            if _match(iface):
                return iface
        for comp in af.components:
            hit = _search_component(comp)
            if hit is not None:
                return hit
        for sys in af.systems:
            hit = _search_system(sys)
            if hit is not None:
                return hit
    return None


def _format_type_ref(type_ref: TypeRef) -> str:
    """Format a TypeRef as a human-readable string."""
    if isinstance(type_ref, PrimitiveTypeRef):
        return type_ref.primitive.value
    if isinstance(type_ref, ListTypeRef):
        return f"List<{_format_type_ref(type_ref.element_type)}>"
    if isinstance(type_ref, MapTypeRef):
        return f"Map<{_format_type_ref(type_ref.key_type)}, {_format_type_ref(type_ref.value_type)}>"
    if isinstance(type_ref, OptionalTypeRef):
        return f"Optional<{_format_type_ref(type_ref.inner_type)}>"
    if isinstance(type_ref, NamedTypeRef):
        return type_ref.name
    return "unknown"
