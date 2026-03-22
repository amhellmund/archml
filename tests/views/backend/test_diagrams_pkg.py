# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the diagrams-package rendering backend."""

from pathlib import Path

from archml.model.entities import Component, ConnectDef, InterfaceRef, System, UserDef
from archml.views.backend.diagrams_pkg import _FORMAT_MAP, _node_class, render_diagrams_pkg
from archml.views.topology import build_viz_diagram, build_viz_diagram_all

# ###############
# Helpers
# ###############


def _iref(name: str, version: str | None = None) -> InterfaceRef:
    return InterfaceRef(name=name, version=version)


def _connect(src_entity: str, src_port: str, dst_entity: str, dst_port: str, channel: str | None = None) -> ConnectDef:
    return ConnectDef(
        src_entity=src_entity, src_port=src_port, channel=channel, dst_entity=dst_entity, dst_port=dst_port
    )


def _render_svg(entity: Component | System, tmp_path: Path, **kwargs: object) -> Path:
    """Build a VizDiagram and render to SVG via the diagrams backend."""
    diagram = build_viz_diagram(entity)
    out = tmp_path / "diagram.svg"
    render_diagrams_pkg(diagram, out, **kwargs)
    return out


# ###############
# _node_class unit tests
# ###############


def test_node_class_component() -> None:
    from diagrams.generic.compute import Rack

    assert _node_class("component") is Rack


def test_node_class_external_component() -> None:
    from diagrams.generic.compute import Rack

    assert _node_class("external_component") is Rack


def test_node_class_system() -> None:
    from diagrams.generic.place import Datacenter

    assert _node_class("system") is Datacenter


def test_node_class_external_system() -> None:
    from diagrams.generic.place import Datacenter

    assert _node_class("external_system") is Datacenter


def test_node_class_user() -> None:
    from diagrams.onprem.client import Users

    assert _node_class("user") is Users


def test_node_class_external_user() -> None:
    from diagrams.onprem.client import Users

    assert _node_class("external_user") is Users


def test_node_class_channel() -> None:
    from diagrams.generic.network import Switch

    assert _node_class("channel") is Switch


def test_node_class_interface() -> None:
    from diagrams.generic.blank import Blank

    assert _node_class("interface") is Blank


def test_node_class_terminal() -> None:
    from diagrams.generic.blank import Blank

    assert _node_class("terminal") is Blank


def test_node_class_none() -> None:
    from diagrams.generic.blank import Blank

    assert _node_class(None) is Blank


# ###############
# Format map
# ###############


def test_format_map_contains_svg() -> None:
    assert _FORMAT_MAP[".svg"] == "svg"


def test_format_map_contains_pdf() -> None:
    assert _FORMAT_MAP[".pdf"] == "pdf"


# ###############
# File creation
# ###############


def test_render_creates_svg_file(tmp_path: Path) -> None:
    """render_diagrams_pkg writes an SVG file at the specified output path."""
    comp = Component(name="Worker")
    diagram = build_viz_diagram(comp)
    out = tmp_path / "out.svg"
    render_diagrams_pkg(diagram, out)
    assert out.exists()


def test_render_creates_parent_directory(tmp_path: Path) -> None:
    """render_diagrams_pkg creates missing parent directories."""
    comp = Component(name="Worker")
    diagram = build_viz_diagram(comp)
    out = tmp_path / "nested" / "deep" / "diagram.svg"
    render_diagrams_pkg(diagram, out)
    assert out.exists()


def test_render_svg_content_is_nonempty(tmp_path: Path) -> None:
    """The rendered SVG file has non-zero size."""
    out = _render_svg(Component(name="Worker"), tmp_path)
    assert out.stat().st_size > 0


def test_render_unknown_extension_produces_svg(tmp_path: Path) -> None:
    """An unrecognised extension is replaced with .svg in the output file."""
    comp = Component(name="Worker")
    diagram = build_viz_diagram(comp)
    out = tmp_path / "diagram.diag"
    render_diagrams_pkg(diagram, out)
    # diagrams appends .svg when extension is unknown
    assert (tmp_path / "diagram.svg").exists()


# ###############
# Node kinds
# ###############


def test_render_system_with_components(tmp_path: Path) -> None:
    """A system with multiple components renders without error."""
    sys = System(
        name="ECommerce",
        components=[
            Component(name="OrderService", provides=[_iref("OrderConfirmation")], requires=[_iref("PaymentRequest")]),
            Component(name="PaymentGateway", provides=[_iref("PaymentRequest")], requires=[_iref("PaymentResult")]),
        ],
        connects=[
            _connect("PaymentGateway", "PaymentRequest", "OrderService", "PaymentRequest"),
        ],
    )
    out = _render_svg(sys, tmp_path)
    assert out.exists()


def test_render_system_with_user(tmp_path: Path) -> None:
    """A system containing a user node renders without error."""
    sys = System(
        name="Shop",
        users=[UserDef(name="Customer")],
        components=[Component(name="Checkout")],
    )
    out = _render_svg(sys, tmp_path)
    assert out.exists()


def test_render_component_with_requires_and_provides(tmp_path: Path) -> None:
    """A component with interface ports produces a diagram with peripheral terminal nodes."""
    comp = Component(
        name="Processor",
        requires=[_iref("InputData")],
        provides=[_iref("OutputData")],
    )
    out = _render_svg(comp, tmp_path)
    assert out.exists()


def test_render_with_channel(tmp_path: Path) -> None:
    """A connect statement with a named channel produces a channel node in the diagram."""
    sys = System(
        name="Messenger",
        components=[
            Component(name="Producer", provides=[_iref("Msg")]),
            Component(name="Consumer", requires=[_iref("Msg")]),
        ],
        connects=[_connect("Producer", "Msg", "Consumer", "Msg", channel="bus")],
    )
    out = _render_svg(sys, tmp_path)
    assert out.exists()


def test_render_all_diagram(tmp_path: Path) -> None:
    """build_viz_diagram_all with the diagrams backend renders without error."""
    from archml.compiler.build import SourceImportKey, compile_files

    archml_src = tmp_path / "arch.archml"
    archml_src.write_text(
        "system Alpha {\n  component Foo {}\n}\nsystem Beta {\n  component Bar {}\n}\n",
        encoding="utf-8",
    )
    workspace_yaml = tmp_path / ".archml-workspace.yaml"
    workspace_yaml.write_text("name: ws\nbuild-directory: .build\nsource-imports:\n  - name: ws\n    local-path: .\n")

    build_dir = tmp_path / ".build"
    compiled = compile_files([archml_src], build_dir, {SourceImportKey("ws", "ws"): tmp_path})

    diagram = build_viz_diagram_all(compiled)
    out = tmp_path / "all.svg"
    render_diagrams_pkg(diagram, out)
    assert out.exists()


# ###############
# Direction parameter
# ###############


def test_render_tb_direction(tmp_path: Path) -> None:
    """direction='TB' renders without error."""
    comp = Component(name="Worker")
    diagram = build_viz_diagram(comp)
    out = tmp_path / "out.svg"
    render_diagrams_pkg(diagram, out, direction="TB")
    assert out.exists()
