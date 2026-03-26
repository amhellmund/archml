# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Sphinx extension implementation for embedding ArchML architecture views.

Usage in ``conf.py``::

    extensions = ["archml.sphinx_ext"]

Usage in RST::

    .. archml-visualize::
       :root: Order::A
       :depth: 0
       :image-width: 400px

    .. archml-explorer::
       :height: 800px

The ``archml-visualize`` directive compiles the ArchML workspace and renders
the requested entity as an SVG, injecting a standard ``image`` node.  The SVG
is written to ``<srcdir>/_archml_images/``.

The ``archml-explorer`` directive generates the full self-contained interactive
HTML viewer and embeds it as an ``<iframe>``.  The HTML is written to
``<srcdir>/_archml_explorer/index.html`` and copied to the output directory
during the ``build-finished`` event (HTML builder only).
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from docutils import nodes
from docutils.parsers.rst import Directive, directives

if TYPE_CHECKING:
    from sphinx.application import Sphinx

# ###############
# Public Interface
# ###############


def setup(app: Sphinx) -> dict[str, Any]:
    """Register the ``archml-visualize`` directive with Sphinx.

    Add ``"archml.sphinx_ext"`` to the ``extensions`` list in ``conf.py``
    to activate this extension.

    Configuration values (set in ``conf.py``):

    ``archml_workspace_dir``
        Path to the directory containing ``.archml-workspace.yaml``.  May be
        absolute or relative to the Sphinx source directory.  When omitted,
        the extension walks up from the source directory until it finds the
        workspace file.

    Args:
        app: The Sphinx application instance.

    Returns:
        Extension metadata dict consumed by Sphinx.
    """
    app.add_config_value("archml_workspace_dir", default=None, rebuild="env")
    app.add_directive("archml-visualize", ArchmlVisualizeDirective)
    app.add_directive("archml-explorer", ArchmlExplorerDirective)
    app.connect("build-finished", _copy_explorer_static)
    return {
        "version": "0.1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }


class ArchmlVisualizeDirective(Directive):
    """Directive that generates and embeds an ArchML architecture diagram.

    Options:
        root: ``::``-delimited entity path to visualize (e.g. ``Order::A``).
            Required.
        depth: Maximum expansion depth.  ``0`` renders the entity as an
            opaque box; omit for full depth.  Optional.
        image-width: CSS width for the rendered image (e.g. ``400px``).
            Optional.
    """

    required_arguments = 0
    optional_arguments = 0
    option_spec = {
        "root": directives.unchanged_required,
        "depth": directives.nonnegative_int,
        "image-width": directives.unchanged,
    }
    has_content = False

    def run(self) -> list[nodes.Node]:
        """Generate the SVG diagram and return a ``nodes.image`` node."""
        env = self.state.document.settings.env
        root_entity: str = self.options["root"]
        depth: int | None = self.options.get("depth")
        image_width: str | None = self.options.get("image-width")

        try:
            svg_path = _generate_diagram(env, root_entity, depth)
        except _DiagramError as exc:
            error = self.state_machine.reporter.error(
                str(exc),
                nodes.literal_block(self.block_text, self.block_text),
                line=self.lineno,
            )
            return [error]

        # Compute URI relative to the source document's directory so Sphinx
        # can resolve and copy the image to the output directory.
        doc_dir = Path(env.srcdir) / Path(env.docname).parent
        rel_uri = os.path.relpath(svg_path, doc_dir).replace("\\", "/")

        image_node = nodes.image(uri=rel_uri)
        image_node["candidates"] = {"*": rel_uri}
        if image_width:
            image_node["width"] = image_width
        return [image_node]


class ArchmlExplorerDirective(Directive):
    """Directive that generates and embeds the full interactive ArchML explorer.

    The directive compiles the entire ArchML workspace into a self-contained
    HTML viewer and embeds it as an ``<iframe>``.  Only rendered by the HTML
    builder; other builders produce no output.

    Options:
        height: CSS height of the iframe (e.g. ``800px``).  Defaults to
            ``600px``.
        width: CSS width of the iframe (e.g. ``100%``).  Defaults to ``100%``.
        width-optimized: Flag.  When present, combines the left and right
            sidebars into a single left sidebar and adds a top bar with a
            hamburger toggle.  Saves horizontal space for narrow viewports.
    """

    required_arguments = 0
    optional_arguments = 0
    option_spec = {
        "height": directives.unchanged,
        "width": directives.unchanged,
        "width-optimized": directives.flag,
    }
    has_content = False

    def run(self) -> list[nodes.Node]:
        """Generate the explorer HTML and return a ``nodes.raw`` iframe node."""
        env = self.state.document.settings.env
        height: str = self.options.get("height", "600px")
        width: str = self.options.get("width", "100%")
        width_optimized: bool = "width-optimized" in self.options

        try:
            html_path = _generate_explorer_html(env, width_optimized=width_optimized)
        except _ExplorerError as exc:
            error = self.state_machine.reporter.error(
                str(exc),
                nodes.literal_block(self.block_text, self.block_text),
                line=self.lineno,
            )
            return [error]

        doc_dir = Path(env.srcdir) / Path(env.docname).parent
        rel_uri = os.path.relpath(html_path, doc_dir).replace("\\", "/")

        iframe = f'<iframe src="{rel_uri}" width="{width}" height="{height}" style="border:none;"></iframe>'
        return [nodes.raw("", iframe, format="html")]


def find_workspace_root(start: Path) -> Path | None:
    """Walk up from *start* to find the nearest ``.archml-workspace.yaml``.

    Args:
        start: Directory from which to begin the upward search.

    Returns:
        The directory containing the workspace file, or ``None`` if not found.
    """
    current = start.resolve()
    while True:
        if (current / ".archml-workspace.yaml").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


# ################
# Implementation
# ################


class _DiagramError(Exception):
    """Raised when diagram generation fails for any reason."""


class _ExplorerError(Exception):
    """Raised when explorer HTML generation fails for any reason."""


def _sanitize_name(name: str) -> str:
    """Return a filename-safe version of an entity path.

    Replaces any character that is not alphanumeric, a hyphen, or an
    underscore with an underscore.
    """
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def _generate_diagram(env: Any, root_entity: str, depth: int | None) -> Path:
    """Compile ArchML sources and render an SVG for *root_entity*.

    The SVG is written to ``<srcdir>/_archml_images/<name>.svg`` and the
    absolute path is returned so the caller can compute a relative URI.

    Args:
        env: Sphinx build environment (provides ``srcdir`` and ``docname``).
        root_entity: ``::``-delimited entity path (e.g. ``"Order::A"``).
        depth: Maximum expansion depth passed to the topology builder.

    Returns:
        Absolute :class:`~pathlib.Path` of the generated SVG file.

    Raises:
        _DiagramError: If the workspace cannot be found, compilation fails,
            the entity does not exist, or rendering fails.
    """
    from archml.compiler.build import CompilerError, SourceImportKey, compile_files
    from archml.views.diagram import render_diagram
    from archml.views.layout import compute_layout
    from archml.views.resolver import EntityNotFoundError, resolve_entity
    from archml.views.topology import build_viz_diagram
    from archml.workspace.config import LocalPathImport, WorkspaceConfigError, load_workspace_config

    src_dir = Path(env.srcdir)

    configured_dir: str | None = getattr(env.config, "archml_workspace_dir", None)
    if configured_dir is not None:
        workspace_root = Path(configured_dir)
        if not workspace_root.is_absolute():
            workspace_root = (src_dir / workspace_root).resolve()
        if not (workspace_root / ".archml-workspace.yaml").exists():
            raise _DiagramError(
                f"archml_workspace_dir '{workspace_root}' does not contain a .archml-workspace.yaml file."
            )
    else:
        workspace_root = find_workspace_root(src_dir)
        if workspace_root is None:
            raise _DiagramError(
                f"No ArchML workspace found in '{src_dir}' or any parent directory. "
                "Run 'archml init' to create one, or set 'archml_workspace_dir' in conf.py."
            )

    workspace_yaml = workspace_root / ".archml-workspace.yaml"
    try:
        config = load_workspace_config(workspace_yaml)
    except WorkspaceConfigError as exc:
        raise _DiagramError(f"Cannot load workspace config: {exc}") from exc

    build_dir = workspace_root / config.build_directory

    source_import_map: dict[SourceImportKey, Path] = {}
    for imp in config.source_imports:
        if isinstance(imp, LocalPathImport):
            source_import_map[SourceImportKey(config.name, imp.name)] = (workspace_root / imp.local_path).resolve()

    archml_files = [f for f in workspace_root.rglob("*.archml") if build_dir not in f.parents]
    if not archml_files:
        raise _DiagramError("No .archml files found in the workspace.")

    try:
        compiled = compile_files(archml_files, build_dir, source_import_map)
    except CompilerError as exc:
        raise _DiagramError(f"Compilation failed: {exc}") from exc

    try:
        entity = resolve_entity(compiled, root_entity)
    except EntityNotFoundError as exc:
        raise _DiagramError(str(exc)) from exc

    viz_diagram = build_viz_diagram(entity, depth=depth)
    layout_plan = compute_layout(viz_diagram)

    img_dir = src_dir / "_archml_images"
    img_dir.mkdir(exist_ok=True)

    depth_suffix = f"_d{depth}" if depth is not None else ""
    img_name = f"{_sanitize_name(root_entity)}{depth_suffix}.svg"
    img_path = img_dir / img_name

    render_diagram(viz_diagram, layout_plan, img_path)
    return img_path


def _generate_explorer_html(env: Any, *, width_optimized: bool = False) -> Path:
    """Compile the ArchML workspace and write a self-contained HTML viewer.

    The HTML is written to ``<srcdir>/_archml_explorer/index.html`` and the
    absolute path is returned so the caller can compute a relative URI.

    Args:
        env: Sphinx build environment (provides ``srcdir`` and config).
        width_optimized: When ``True``, generates the viewer in width-optimized
            mode (single left sidebar with top bar and hamburger toggle).

    Returns:
        Absolute :class:`~pathlib.Path` of the generated HTML file.

    Raises:
        _ExplorerError: If the workspace cannot be found, the template is
            missing, or compilation fails.
    """
    from archml.compiler.build import CompilerError, SourceImportKey, compile_files
    from archml.export import build_viewer_payload
    from archml.workspace.config import LocalPathImport, WorkspaceConfigError, load_workspace_config

    src_dir = Path(env.srcdir)

    configured_dir: str | None = getattr(env.config, "archml_workspace_dir", None)
    if configured_dir is not None:
        workspace_root = Path(configured_dir)
        if not workspace_root.is_absolute():
            workspace_root = (src_dir / workspace_root).resolve()
        if not (workspace_root / ".archml-workspace.yaml").exists():
            raise _ExplorerError(
                f"archml_workspace_dir '{workspace_root}' does not contain a .archml-workspace.yaml file."
            )
    else:
        workspace_root = find_workspace_root(src_dir)
        if workspace_root is None:
            raise _ExplorerError(
                f"No ArchML workspace found in '{src_dir}' or any parent directory. "
                "Run 'archml init' to create one, or set 'archml_workspace_dir' in conf.py."
            )

    workspace_yaml = workspace_root / ".archml-workspace.yaml"
    try:
        config = load_workspace_config(workspace_yaml)
    except WorkspaceConfigError as exc:
        raise _ExplorerError(f"Cannot load workspace config: {exc}") from exc

    build_dir = workspace_root / config.build_directory

    source_import_map: dict[SourceImportKey, Path] = {}
    for imp in config.source_imports:
        if isinstance(imp, LocalPathImport):
            source_import_map[SourceImportKey(config.name, imp.name)] = (workspace_root / imp.local_path).resolve()

    archml_files = [f for f in workspace_root.rglob("*.archml") if build_dir not in f.parents]
    if not archml_files:
        raise _ExplorerError("No .archml files found in the workspace.")

    try:
        compiled = compile_files(archml_files, build_dir, source_import_map)
    except CompilerError as exc:
        raise _ExplorerError(f"Compilation failed: {exc}") from exc

    template_path = Path(__file__).parent.parent / "static" / "archml-viewer-template.html"
    if not template_path.exists():
        raise _ExplorerError(
            "ArchML viewer template not found. Run 'python tools/build_js.py' to build the JS bundle first."
        )

    payload_json = build_viewer_payload(compiled, width_optimized=width_optimized)
    data_tag = f'<script id="archml-data" type="application/json">{payload_json}</script>'
    html = template_path.read_text(encoding="utf-8").replace("<!-- ARCHML_DATA_PLACEHOLDER -->", data_tag)

    explorer_dir = src_dir / "_archml_explorer"
    explorer_dir.mkdir(exist_ok=True)
    html_path = explorer_dir / "index.html"
    html_path.write_text(html, encoding="utf-8")
    return html_path


def _copy_explorer_static(app: Any, exception: Exception | None) -> None:
    """Copy ``_archml_explorer/`` from srcdir to the HTML output directory.

    Connected to the Sphinx ``build-finished`` event by :func:`setup`.  Does
    nothing when the build raised an exception or the directory was never
    created (i.e. no ``archml-explorer`` directive was used).

    Args:
        app: The Sphinx application instance.
        exception: Non-``None`` if the build failed; the copy is skipped.
    """
    if exception:
        return
    src = Path(app.srcdir) / "_archml_explorer"
    if not src.exists():
        return
    dst = Path(app.outdir) / "_archml_explorer"
    shutil.copytree(src, dst, dirs_exist_ok=True)
