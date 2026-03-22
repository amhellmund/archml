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

The directive compiles the ArchML workspace found in or above the Sphinx
source directory, renders the requested entity as an SVG, and injects a
standard ``image`` node pointing to the generated file.  The SVG is written
to ``<srcdir>/_archml_images/`` so Sphinx copies it to the output directory
alongside other static assets.
"""

from __future__ import annotations

import os
import re
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
    from archml.views.backend.diagram import render_diagram
    from archml.views.layout_graphviz import compute_layout
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
