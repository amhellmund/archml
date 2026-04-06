# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the archml.sphinx_ext Sphinx extension."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from docutils import nodes

from archml.sphinx_ext import ArchmlVisualizeDirective, find_workspace_root, setup
from archml.sphinx_ext.extension import (
    _DiagramError,
    _generate_diagram,
    _sanitize_name,
)

# ###############
# Fixtures
# ###############

_MINIMAL_WORKSPACE = "name: src\nbuild-directory: .farchml-build\nsource-imports:\n  - name: src\n    local-path: .\n"

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
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    svg_path = _generate_diagram(env, "OrderProcessor", None)

    assert svg_path.exists()
    assert svg_path.suffix == ".svg"


def test_generate_diagram_svg_content_is_valid_xml(tmp_path: Path) -> None:
    """The generated SVG file contains valid XML starting with an XML declaration."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    svg_path = _generate_diagram(env, "OrderProcessor", None)

    content = svg_path.read_text()
    assert content.startswith("<?xml")
    assert "<svg" in content


def test_generate_diagram_places_svg_in_archml_images(tmp_path: Path) -> None:
    """The SVG is written into the _archml_images subdirectory of srcdir."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    svg_path = _generate_diagram(env, "OrderProcessor", None)

    assert svg_path.parent == tmp_path / "_archml_images"


def test_generate_diagram_filename_encodes_entity(tmp_path: Path) -> None:
    """The SVG filename is derived from the entity path."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    svg_path = _generate_diagram(env, "OrderProcessor", None)

    assert "OrderProcessor" in svg_path.name


def test_generate_diagram_filename_encodes_depth(tmp_path: Path) -> None:
    """When depth is given, the filename includes a depth suffix."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    svg_path = _generate_diagram(env, "OrderProcessor", 0)

    assert "_d0" in svg_path.name


def test_generate_diagram_no_depth_suffix_when_depth_is_none(tmp_path: Path) -> None:
    """When depth is None, no depth suffix is added to the filename."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

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
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    with pytest.raises(_DiagramError):
        _generate_diagram(env, "NonExistent", None)


def test_generate_diagram_raises_when_no_archml_files(tmp_path: Path) -> None:
    """_generate_diagram raises _DiagramError when the workspace has no .farchml files."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)

    env = _make_env(tmp_path)
    with pytest.raises(_DiagramError, match="No .farchml files"):
        _generate_diagram(env, "OrderProcessor", None)


def test_generate_diagram_finds_workspace_above_srcdir(tmp_path: Path) -> None:
    """_generate_diagram finds the workspace when srcdir is a subdirectory of it."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

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
    (ws_dir / "arch.farchml").write_text(_SIMPLE_ARCHML)

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    # srcdir has no workspace; it is supplied via config instead.
    env = _make_env(docs_dir, workspace_dir=str(ws_dir))
    svg_path = _generate_diagram(env, "OrderProcessor", None)

    assert svg_path.exists()


def test_generate_diagram_configured_dir_relative_to_srcdir(tmp_path: Path) -> None:
    """A relative archml_workspace_dir is resolved against srcdir."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

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
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    directive = _make_directive({"root": "OrderProcessor"}, tmp_path)
    result = directive.run()

    assert len(result) == 1
    assert isinstance(result[0], nodes.image)


def test_directive_run_image_uri_contains_svg(tmp_path: Path) -> None:
    """The image node URI points to an SVG file."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    directive = _make_directive({"root": "OrderProcessor"}, tmp_path)
    result = directive.run()

    assert result[0]["uri"].endswith(".svg")


def test_directive_run_sets_image_width(tmp_path: Path) -> None:
    """When image-width is given, the image node carries a width attribute."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    directive = _make_directive({"root": "OrderProcessor", "image-width": "400px"}, tmp_path)
    result = directive.run()

    assert result[0]["width"] == "400px"


def test_directive_run_no_width_when_not_specified(tmp_path: Path) -> None:
    """When image-width is omitted, the image node has no width attribute."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    directive = _make_directive({"root": "OrderProcessor"}, tmp_path)
    result = directive.run()

    assert "width" not in result[0].attributes or result[0].get("width") is None


def test_directive_run_returns_error_node_on_missing_entity(tmp_path: Path) -> None:
    """run() returns an error system_message when the entity is not found."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

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
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    # Document lives in a subdirectory of srcdir.
    directive = _make_directive({"root": "OrderProcessor"}, tmp_path, docname="guide/index")
    result = directive.run()

    assert isinstance(result[0], nodes.image)
    # The URI must navigate up from guide/ to reach _archml_images/ at root.
    assert result[0]["uri"].startswith("../_archml_images/")


# ###############
# ArchmlVisualizeDirective — variant option
# ###############


_VARIANT_ARCHML = "interface IFoo {}\ncomponent<cloud> CloudOnly { provides IFoo }\ncomponent Base { provides IFoo }\n"


def test_directive_variant_all_returns_image_node(tmp_path: Path) -> None:
    """variant:all produces a valid image node (same as no variant)."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    directive = _make_directive({"root": "OrderProcessor", "variant": "all"}, tmp_path)
    result = directive.run()

    assert len(result) == 1
    assert isinstance(result[0], nodes.image)


def test_directive_variant_baseline_returns_image_node(tmp_path: Path) -> None:
    """variant:baseline produces a valid image node."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    directive = _make_directive({"root": "OrderProcessor", "variant": "baseline"}, tmp_path)
    result = directive.run()

    assert len(result) == 1
    assert isinstance(result[0], nodes.image)


def test_directive_user_defined_variant_returns_image_node(tmp_path: Path) -> None:
    """A user-defined variant name produces a valid image node."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_VARIANT_ARCHML)

    directive = _make_directive({"root": "Base", "variant": "cloud"}, tmp_path)
    result = directive.run()

    assert len(result) == 1
    assert isinstance(result[0], nodes.image)


def test_directive_variant_all_svg_filename_has_no_variant_suffix(tmp_path: Path) -> None:
    """variant:all does not add a variant suffix to the SVG filename."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    directive = _make_directive({"root": "OrderProcessor", "variant": "all"}, tmp_path)
    result = directive.run()

    assert "_v" not in result[0]["uri"]


def test_directive_variant_baseline_svg_filename_has_variant_suffix(tmp_path: Path) -> None:
    """variant:baseline adds a _vbaseline suffix to the SVG filename."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    directive = _make_directive({"root": "OrderProcessor", "variant": "baseline"}, tmp_path)
    result = directive.run()

    assert "_vbaseline" in result[0]["uri"]


def test_directive_user_defined_variant_svg_filename_has_variant_suffix(tmp_path: Path) -> None:
    """A user-defined variant name adds a _v<name> suffix to the SVG filename."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_VARIANT_ARCHML)

    directive = _make_directive({"root": "Base", "variant": "cloud"}, tmp_path)
    result = directive.run()

    assert "_vcloud" in result[0]["uri"]


def test_generate_diagram_variant_all_maps_to_no_filter(tmp_path: Path) -> None:
    """Passing variant=None (from 'all') and omitting variant produce the same SVG name."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    path_no_variant = _generate_diagram(env, "OrderProcessor", None, variant=None)
    assert "_v" not in path_no_variant.name


def test_generate_diagram_variant_baseline_creates_separate_svg(tmp_path: Path) -> None:
    """variant='baseline' produces a separate SVG from the unfiltered diagram."""
    (tmp_path / ".archml-workspace.yaml").write_text(_MINIMAL_WORKSPACE)
    (tmp_path / "arch.farchml").write_text(_SIMPLE_ARCHML)

    env = _make_env(tmp_path)
    path_all = _generate_diagram(env, "OrderProcessor", None, variant=None)
    path_baseline = _generate_diagram(env, "OrderProcessor", None, variant="baseline")

    assert path_all != path_baseline
    assert path_baseline.exists()
    assert "_vbaseline" in path_baseline.name
