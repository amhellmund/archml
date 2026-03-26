# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the archml.sphinx_ext Sphinx extension."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from docutils import nodes

from archml.sphinx_ext import ArchmlExplorerDirective, ArchmlVisualizeDirective, find_workspace_root, setup
from archml.sphinx_ext.extension import (
    _copy_explorer_static,
    _DiagramError,
    _ExplorerError,
    _generate_diagram,
    _generate_explorer_html,
    _sanitize_name,
)

# ###############
# Fixtures
# ###############

_MINIMAL_WORKSPACE = "name: src\nbuild-directory: .archml-build\nsource-imports:\n  - name: src\n    local-path: .\n"

_SIMPLE_ARCHML = "component OrderProcessor {}\n"


def _make_env(srcdir: Path, docname: str = "index", workspace_dir: str | None = None) -> MagicMock:
    """Return a mock Sphinx env with ``srcdir``, ``docname``, and optional ``archml_workspace_dir`` set."""
    env = MagicMock()
    env.srcdir = str(srcdir)
    env.docname = docname
    env.config.archml_workspace_dir = workspace_dir
    return env


def _make_directive(
    options: dict, srcdir: Path, docname: str = "index", workspace_dir: str | None = None
) -> ArchmlVisualizeDirective:
    """Instantiate an ArchmlVisualizeDirective with mocked docutils state."""
    env = _make_env(srcdir, docname, workspace_dir=workspace_dir)
    state = MagicMock()
    state.document.settings.env = env
    return ArchmlVisualizeDirective(
        name="archml-visualize",
        arguments=[],
        options=options,
        content=[],
        lineno=1,
        content_offset=0,
        block_text="",
        state=state,
        state_machine=MagicMock(),
    )


def _make_explorer_directive(
    options: dict, srcdir: Path, docname: str = "index", workspace_dir: str | None = None
) -> ArchmlExplorerDirective:
    """Instantiate an ArchmlExplorerDirective with mocked docutils state."""
    env = _make_env(srcdir, docname, workspace_dir=workspace_dir)
    state = MagicMock()
    state.document.settings.env = env
    return ArchmlExplorerDirective(
        name="archml-explorer",
        arguments=[],
        options=options,
        content=[],
        lineno=1,
        content_offset=0,
        block_text="",
        state=state,
        state_machine=MagicMock(),
    )


# ###############
# find_workspace_root
# ###############


def test_find_workspace_root_finds_workspace_in_same_dir(tmp_path: Path) -> None:
    """find_workspace_root returns the directory when the workspace file is there."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    assert find_workspace_root(tmp_path) == tmp_path


def test_find_workspace_root_walks_up(tmp_path: Path) -> None:
    """find_workspace_root walks up parent directories to find the workspace."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    subdir = tmp_path / "a" / "b" / "c"
    subdir.mkdir(parents=True)
    assert find_workspace_root(subdir) == tmp_path


def test_find_workspace_root_returns_none_when_not_found(tmp_path: Path) -> None:
    """find_workspace_root returns None when no workspace file is found."""
    assert find_workspace_root(tmp_path) is None


def test_find_workspace_root_stops_at_closest_ancestor(tmp_path: Path) -> None:
    """find_workspace_root returns the nearest workspace, not a more distant ancestor."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    inner = tmp_path / "sub"
    inner.mkdir()
    (inner / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    assert find_workspace_root(inner) == inner


# ###############
# _sanitize_name
# ###############


def test_sanitize_name_replaces_colons(tmp_path: Path) -> None:
    """Double-colon separators are replaced with underscores."""
    assert _sanitize_name("Order::A") == "Order__A"


def test_sanitize_name_preserves_alphanumeric(tmp_path: Path) -> None:
    """Alphanumeric characters and underscores/hyphens are preserved."""
    assert _sanitize_name("MySystem_123-x") == "MySystem_123-x"


def test_sanitize_name_replaces_spaces(tmp_path: Path) -> None:
    """Spaces are replaced with underscores."""
    assert _sanitize_name("My System") == "My_System"


# ###############
# setup()
# ###############


def test_setup_registers_directive() -> None:
    """setup() registers the archml-visualize directive with the Sphinx app."""
    app = MagicMock()
    setup(app)
    app.add_directive.assert_any_call("archml-visualize", ArchmlVisualizeDirective)


def test_setup_registers_explorer_directive() -> None:
    """setup() registers the archml-explorer directive with the Sphinx app."""
    app = MagicMock()
    setup(app)
    app.add_directive.assert_any_call("archml-explorer", ArchmlExplorerDirective)


def test_setup_connects_build_finished() -> None:
    """setup() connects the build-finished event for copying the explorer output."""
    app = MagicMock()
    setup(app)
    app.connect.assert_called_once_with("build-finished", _copy_explorer_static)


def test_setup_returns_version() -> None:
    """setup() returns a metadata dict with a version key."""
    app = MagicMock()
    result = setup(app)
    assert "version" in result
    assert isinstance(result["version"], str)


def test_setup_declares_parallel_read_safe() -> None:
    """setup() marks the extension as parallel-read-safe."""
    app = MagicMock()
    result = setup(app)
    assert result["parallel_read_safe"] is True


def test_setup_declares_parallel_write_safe() -> None:
    """setup() marks the extension as parallel-write-safe."""
    app = MagicMock()
    result = setup(app)
    assert result["parallel_write_safe"] is True


# ###############
# _generate_diagram
# ###############


def test_generate_diagram_creates_svg(tmp_path: Path) -> None:
    """_generate_diagram writes an SVG file and returns its path."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    svg_path = _generate_diagram(env, "OrderProcessor", None)

    assert svg_path.exists()
    assert svg_path.suffix == ".svg"


def test_generate_diagram_svg_content_is_valid_xml(tmp_path: Path) -> None:
    """The generated SVG file contains valid XML starting with an XML declaration."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    svg_path = _generate_diagram(env, "OrderProcessor", None)

    content = svg_path.read_text()
    assert content.startswith("<?xml")
    assert "<svg" in content


def test_generate_diagram_places_svg_in_archml_images(tmp_path: Path) -> None:
    """The SVG is written into the _archml_images subdirectory of srcdir."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    svg_path = _generate_diagram(env, "OrderProcessor", None)

    assert svg_path.parent == tmp_path / "_archml_images"


def test_generate_diagram_filename_encodes_entity(tmp_path: Path) -> None:
    """The SVG filename is derived from the entity path."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    svg_path = _generate_diagram(env, "OrderProcessor", None)

    assert "OrderProcessor" in svg_path.name


def test_generate_diagram_filename_encodes_depth(tmp_path: Path) -> None:
    """When depth is given, the filename includes a depth suffix."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    svg_path = _generate_diagram(env, "OrderProcessor", 0)

    assert "_d0" in svg_path.name


def test_generate_diagram_no_depth_suffix_when_depth_is_none(tmp_path: Path) -> None:
    """When depth is None, no depth suffix is added to the filename."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    svg_path = _generate_diagram(env, "OrderProcessor", None)

    assert "_d" not in svg_path.name


def test_generate_diagram_raises_when_no_workspace(tmp_path: Path) -> None:
    """_generate_diagram raises _DiagramError when no workspace is found."""
    env = _make_env(tmp_path)
    with pytest.raises(_DiagramError, match="No ArchML workspace"):
        _generate_diagram(env, "OrderProcessor", None)


def test_generate_diagram_raises_when_entity_not_found(tmp_path: Path) -> None:
    """_generate_diagram raises _DiagramError when the entity path does not exist."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    with pytest.raises(_DiagramError):
        _generate_diagram(env, "NonExistent", None)


def test_generate_diagram_raises_when_no_archml_files(tmp_path: Path) -> None:
    """_generate_diagram raises _DiagramError when the workspace has no .archml files."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)

    env = _make_env(tmp_path)
    with pytest.raises(_DiagramError, match="No .archml files"):
        _generate_diagram(env, "OrderProcessor", None)


def test_generate_diagram_finds_workspace_above_srcdir(tmp_path: Path) -> None:
    """_generate_diagram finds the workspace when srcdir is a subdirectory of it."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    env = _make_env(docs_dir)
    svg_path = _generate_diagram(env, "OrderProcessor", None)

    assert svg_path.exists()


def test_generate_diagram_uses_configured_workspace_dir(tmp_path: Path) -> None:
    """_generate_diagram uses archml_workspace_dir from config when set."""
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    (ws_dir / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (ws_dir / "arch.archml").write_text(_SIMPLE_ARCHML)

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    # srcdir has no workspace; it is supplied via config instead.
    env = _make_env(docs_dir, workspace_dir=str(ws_dir))
    svg_path = _generate_diagram(env, "OrderProcessor", None)

    assert svg_path.exists()


def test_generate_diagram_configured_dir_relative_to_srcdir(tmp_path: Path) -> None:
    """A relative archml_workspace_dir is resolved against srcdir."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    # Relative path pointing from docs/ up one level to the workspace.
    env = _make_env(docs_dir, workspace_dir="..")
    svg_path = _generate_diagram(env, "OrderProcessor", None)

    assert svg_path.exists()


def test_generate_diagram_configured_dir_missing_workspace_yaml(tmp_path: Path) -> None:
    """_generate_diagram raises _DiagramError when the configured dir has no workspace file."""
    env = _make_env(tmp_path, workspace_dir=str(tmp_path))
    with pytest.raises(_DiagramError, match="archml_workspace_dir"):
        _generate_diagram(env, "OrderProcessor", None)


# ###############
# setup() — config registration
# ###############


def test_setup_registers_workspace_dir_config() -> None:
    """setup() registers the archml_workspace_dir config value."""
    app = MagicMock()
    setup(app)
    app.add_config_value.assert_called_once_with("archml_workspace_dir", default=None, rebuild="env")


# ###############
# ArchmlVisualizeDirective.run()
# ###############


def test_directive_run_returns_image_node(tmp_path: Path) -> None:
    """run() returns a single image node on success."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    directive = _make_directive({"root": "OrderProcessor"}, tmp_path)
    result = directive.run()

    assert len(result) == 1
    assert isinstance(result[0], nodes.image)


def test_directive_run_image_uri_contains_svg(tmp_path: Path) -> None:
    """The image node URI points to an SVG file."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    directive = _make_directive({"root": "OrderProcessor"}, tmp_path)
    result = directive.run()

    assert result[0]["uri"].endswith(".svg")


def test_directive_run_sets_image_width(tmp_path: Path) -> None:
    """When image-width is given, the image node carries a width attribute."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    directive = _make_directive({"root": "OrderProcessor", "image-width": "400px"}, tmp_path)
    result = directive.run()

    assert result[0]["width"] == "400px"


def test_directive_run_no_width_when_not_specified(tmp_path: Path) -> None:
    """When image-width is omitted, the image node has no width attribute."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    directive = _make_directive({"root": "OrderProcessor"}, tmp_path)
    result = directive.run()

    assert "width" not in result[0].attributes or result[0].get("width") is None


def test_directive_run_returns_error_node_on_missing_entity(tmp_path: Path) -> None:
    """run() returns an error system_message when the entity is not found."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    directive = _make_directive({"root": "DoesNotExist"}, tmp_path)
    result = directive.run()

    assert len(result) == 1
    assert not isinstance(result[0], nodes.image)


def test_directive_run_returns_error_node_on_missing_workspace(tmp_path: Path) -> None:
    """run() returns an error system_message when no workspace is found."""
    directive = _make_directive({"root": "OrderProcessor"}, tmp_path)
    result = directive.run()

    assert len(result) == 1
    assert not isinstance(result[0], nodes.image)


def test_directive_run_uri_relative_to_doc_in_subdir(tmp_path: Path) -> None:
    """URI is computed relative to the document directory, not srcdir."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    # Document lives in a subdirectory of srcdir.
    directive = _make_directive({"root": "OrderProcessor"}, tmp_path, docname="guide/index")
    result = directive.run()

    assert isinstance(result[0], nodes.image)
    # The URI must navigate up from guide/ to reach _archml_images/ at root.
    assert result[0]["uri"].startswith("../_archml_images/")


# ###############
# _generate_explorer_html
# ###############


def test_generate_explorer_html_creates_html_file(tmp_path: Path) -> None:
    """_generate_explorer_html writes an HTML file and returns its path."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    html_path = _generate_explorer_html(env)

    assert html_path.exists()
    assert html_path.suffix == ".html"


def test_generate_explorer_html_places_file_in_archml_explorer(tmp_path: Path) -> None:
    """The HTML is written into the _archml_explorer subdirectory of srcdir."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    html_path = _generate_explorer_html(env)

    assert html_path.parent == tmp_path / "_archml_explorer"
    assert html_path.name == "index.html"


def test_generate_explorer_html_content_contains_archml_data(tmp_path: Path) -> None:
    """The generated HTML contains the embedded archml-data script tag."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    html_path = _generate_explorer_html(env)

    content = html_path.read_text(encoding="utf-8")
    assert 'id="archml-data"' in content


def test_generate_explorer_html_raises_when_no_workspace(tmp_path: Path) -> None:
    """_generate_explorer_html raises _ExplorerError when no workspace is found."""
    env = _make_env(tmp_path)
    with pytest.raises(_ExplorerError, match="No ArchML workspace"):
        _generate_explorer_html(env)


def test_generate_explorer_html_raises_when_no_archml_files(tmp_path: Path) -> None:
    """_generate_explorer_html raises _ExplorerError when no .archml files exist."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)

    env = _make_env(tmp_path)
    with pytest.raises(_ExplorerError, match="No .archml files"):
        _generate_explorer_html(env)


def test_generate_explorer_html_raises_when_configured_dir_missing_workspace(tmp_path: Path) -> None:
    """_generate_explorer_html raises _ExplorerError when configured dir has no workspace file."""
    env = _make_env(tmp_path, workspace_dir=str(tmp_path))
    with pytest.raises(_ExplorerError, match="archml_workspace_dir"):
        _generate_explorer_html(env)


# ###############
# _copy_explorer_static
# ###############


def test_copy_explorer_static_copies_directory(tmp_path: Path) -> None:
    """_copy_explorer_static copies _archml_explorer/ from srcdir to outdir."""
    srcdir = tmp_path / "src"
    outdir = tmp_path / "out"
    srcdir.mkdir()
    outdir.mkdir()
    explorer_src = srcdir / "_archml_explorer"
    explorer_src.mkdir()
    (explorer_src / "index.html").write_text("<html/>")

    app = MagicMock()
    app.srcdir = str(srcdir)
    app.outdir = str(outdir)

    _copy_explorer_static(app, None)

    assert (outdir / "_archml_explorer" / "index.html").exists()


def test_copy_explorer_static_skips_when_exception(tmp_path: Path) -> None:
    """_copy_explorer_static does nothing when the build raised an exception."""
    srcdir = tmp_path / "src"
    outdir = tmp_path / "out"
    srcdir.mkdir()
    outdir.mkdir()
    explorer_src = srcdir / "_archml_explorer"
    explorer_src.mkdir()
    (explorer_src / "index.html").write_text("<html/>")

    app = MagicMock()
    app.srcdir = str(srcdir)
    app.outdir = str(outdir)

    _copy_explorer_static(app, RuntimeError("build failed"))

    assert not (outdir / "_archml_explorer").exists()


def test_copy_explorer_static_skips_when_no_explorer_dir(tmp_path: Path) -> None:
    """_copy_explorer_static does nothing when the explorer dir was never created."""
    app = MagicMock()
    app.srcdir = str(tmp_path)
    app.outdir = str(tmp_path / "out")

    # Should not raise even when directory is absent.
    _copy_explorer_static(app, None)


# ###############
# ArchmlExplorerDirective.run()
# ###############


def test_explorer_directive_run_returns_raw_node(tmp_path: Path) -> None:
    """run() returns a single raw HTML node on success."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    directive = _make_explorer_directive({}, tmp_path)
    result = directive.run()

    assert len(result) == 1
    assert isinstance(result[0], nodes.raw)


def test_explorer_directive_run_iframe_src_contains_index_html(tmp_path: Path) -> None:
    """The raw node content contains an iframe pointing to index.html."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    directive = _make_explorer_directive({}, tmp_path)
    result = directive.run()

    assert "index.html" in result[0].astext()


def test_explorer_directive_run_sets_height(tmp_path: Path) -> None:
    """When height is given, the iframe carries that height."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    directive = _make_explorer_directive({"height": "900px"}, tmp_path)
    result = directive.run()

    assert 'height="900px"' in result[0].astext()


def test_explorer_directive_run_default_height(tmp_path: Path) -> None:
    """When height is not given, the iframe defaults to 600px."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    directive = _make_explorer_directive({}, tmp_path)
    result = directive.run()

    assert 'height="600px"' in result[0].astext()


def test_explorer_directive_run_sets_width(tmp_path: Path) -> None:
    """When width is given, the iframe carries that width."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    directive = _make_explorer_directive({"width": "80%"}, tmp_path)
    result = directive.run()

    assert 'width="80%"' in result[0].astext()


def test_explorer_directive_run_returns_error_on_missing_workspace(tmp_path: Path) -> None:
    """run() returns an error system_message when no workspace is found."""
    directive = _make_explorer_directive({}, tmp_path)
    result = directive.run()

    assert len(result) == 1
    assert not isinstance(result[0], nodes.raw)


def test_explorer_directive_run_uri_relative_to_doc_in_subdir(tmp_path: Path) -> None:
    """iframe src is computed relative to the document directory, not srcdir."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    directive = _make_explorer_directive({}, tmp_path, docname="guide/index")
    result = directive.run()

    assert isinstance(result[0], nodes.raw)
    assert "../_archml_explorer/index.html" in result[0].astext()


# ###############
# ArchmlExplorerDirective — width-optimized
# ###############


def test_explorer_directive_width_optimized_embeds_flag(tmp_path: Path) -> None:
    """width-optimized option causes widthOptimized to appear in the generated HTML payload."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    directive = _make_explorer_directive({"width-optimized": None}, tmp_path)
    result = directive.run()

    assert isinstance(result[0], nodes.raw)
    html_path = tmp_path / "_archml_explorer" / "index.html"
    assert "widthOptimized" in html_path.read_text(encoding="utf-8")


def test_explorer_directive_without_width_optimized_no_flag(tmp_path: Path) -> None:
    """Without width-optimized option, widthOptimized is absent from the generated HTML payload."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    directive = _make_explorer_directive({}, tmp_path)
    directive.run()

    html_path = tmp_path / "_archml_explorer" / "index.html"
    assert "widthOptimized" not in html_path.read_text(encoding="utf-8")


def test_generate_explorer_html_width_optimized_embeds_flag(tmp_path: Path) -> None:
    """_generate_explorer_html with width_optimized=True embeds widthOptimized in the HTML."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    html_path = _generate_explorer_html(env, width_optimized=True)

    assert "widthOptimized" in html_path.read_text(encoding="utf-8")


def test_generate_explorer_html_default_no_width_optimized_flag(tmp_path: Path) -> None:
    """_generate_explorer_html without width_optimized does not embed widthOptimized."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.archml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    html_path = _generate_explorer_html(env)

    assert "widthOptimized" not in html_path.read_text(encoding="utf-8")
