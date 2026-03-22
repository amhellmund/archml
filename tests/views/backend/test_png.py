# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the PNG diagram rendering backend."""

import struct
from pathlib import Path

import pytest

from archml.model.entities import Component, ConnectDef, InterfaceRef, System, UserDef
from archml.views.backend.png import render_png
from archml.views.layout_graphviz import compute_layout
from archml.views.topology import build_viz_diagram

# ###############
# Helpers
# ###############


def _iref(name: str, version: str | None = None) -> InterfaceRef:
    return InterfaceRef(name=name, version=version)


def _connect(src_entity: str, src_port: str, dst_entity: str, dst_port: str, channel: str | None = None) -> ConnectDef:
    return ConnectDef(
        src_entity=src_entity, src_port=src_port, channel=channel, dst_entity=dst_entity, dst_port=dst_port
    )


def _render(entity: Component | System, tmp_path: Path, **kwargs: object) -> Path:
    """Build a VizDiagram + LayoutPlan, render to PNG, and return the output path."""
    diagram = build_viz_diagram(entity)
    plan = compute_layout(diagram)
    out = tmp_path / "diagram.png"
    render_png(diagram, plan, out, **kwargs)
    return out


def _png_dimensions(path: Path) -> tuple[int, int]:
    """Read width and height from PNG IHDR chunk (no external dependency needed)."""
    data = path.read_bytes()
    # PNG signature is 8 bytes; IHDR chunk data starts at byte 16.
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "Not a valid PNG file"
    width = struct.unpack(">I", data[16:20])[0]
    height = struct.unpack(">I", data[20:24])[0]
    return width, height


# ###############
# File creation
# ###############


def test_render_png_creates_file(tmp_path: Path) -> None:
    """render_png writes a file at the specified output path."""
    comp = Component(name="Worker", components=[Component(name="A")])
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    out = tmp_path / "out.png"
    render_png(diagram, plan, out)
    assert out.exists()


def test_render_png_creates_parent_directory(tmp_path: Path) -> None:
    """render_png creates missing parent directories."""
    comp = Component(name="Worker", components=[Component(name="A")])
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    out = tmp_path / "nested" / "deep" / "diagram.png"
    render_png(diagram, plan, out)
    assert out.exists()


def test_render_png_output_is_valid_png(tmp_path: Path) -> None:
    """Output file has a valid PNG signature."""
    comp = Component(name="Worker", components=[Component(name="A")])
    out = _render(comp, tmp_path)
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


# ###############
# Dimensions
# ###############


def test_render_png_dimensions_match_scale(tmp_path: Path) -> None:
    """PNG dimensions equal plan total dimensions multiplied by scale."""
    comp = Component(name="Sys", components=[Component(name="A")])
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    scale = 2.0
    out = tmp_path / "out.png"
    render_png(diagram, plan, out, scale=scale)
    w, h = _png_dimensions(out)
    assert w == pytest.approx(plan.total_width * scale, abs=1)
    assert h == pytest.approx(plan.total_height * scale, abs=1)


def test_render_png_larger_scale_produces_larger_image(tmp_path: Path) -> None:
    """Applying a larger scale produces a larger PNG."""
    comp = Component(name="Sys", components=[Component(name="A")])
    diagram = build_viz_diagram(comp)
    plan = compute_layout(diagram)
    out1 = tmp_path / "s1.png"
    out2 = tmp_path / "s2.png"
    render_png(diagram, plan, out1, scale=1.0)
    render_png(diagram, plan, out2, scale=3.0)
    w1, h1 = _png_dimensions(out1)
    w2, h2 = _png_dimensions(out2)
    assert w2 > w1
    assert h2 > h1


# ###############
# Node kinds / channel rendering
# ###############


def test_render_png_with_child_components(tmp_path: Path) -> None:
    """A system with child components renders without error."""
    sys = System(
        name="Root",
        components=[Component(name="Alpha"), Component(name="Beta")],
    )
    out = _render(sys, tmp_path)
    assert out.exists()


def test_render_png_with_channel_nodes(tmp_path: Path) -> None:
    """A system with channel connects (channel nodes) renders without error."""
    a = Component(name="A", requires=[_iref("IFace")])
    b = Component(name="B", provides=[_iref("IFace")])
    sys = System(
        name="Root",
        connects=[_connect("B", "IFace", "A", "IFace", channel="ch")],
        components=[a, b],
    )
    out = _render(sys, tmp_path)
    assert out.exists()
    w, h = _png_dimensions(out)
    assert w > 0
    assert h > 0


def test_render_png_with_user_nodes(tmp_path: Path) -> None:
    """A system with user nodes renders without error."""
    customer = UserDef(name="Customer", provides=[InterfaceRef(name="OrderRequest")])
    order_svc = Component(name="OrderService", requires=[InterfaceRef(name="OrderRequest")])
    sys = System(
        name="ECommerce",
        connects=[
            ConnectDef(
                src_entity="Customer",
                src_port="OrderRequest",
                channel="order_in",
                dst_entity="OrderService",
                dst_port="OrderRequest",
            )
        ],
        users=[customer],
        components=[order_svc],
    )
    out = _render(sys, tmp_path)
    assert out.exists()


def test_render_png_minimal_entity(tmp_path: Path) -> None:
    """A minimal entity with one child renders a PNG without error."""
    comp = Component(name="Leaf", components=[Component(name="A")])
    out = _render(comp, tmp_path)
    assert out.exists()
    w, h = _png_dimensions(out)
    assert w > 0
    assert h > 0


def test_render_png_with_peripheral_terminals(tmp_path: Path) -> None:
    """A system with requires/provides terminals renders without error."""
    comp = Component(
        name="Sys",
        requires=[_iref("DataFeed")],
        provides=[_iref("Result")],
        components=[Component(name="Worker")],
    )
    out = _render(comp, tmp_path)
    assert out.exists()


# ###############
# Integration
# ###############


def test_render_png_ecommerce_system(tmp_path: Path) -> None:
    """Full integration: multi-component system with channels renders a valid PNG."""
    sys = System(
        name="ECommerce",
        connects=[
            _connect("PaymentService", "PaymentRequest", "OrderService", "PaymentRequest", channel="payment"),
            _connect("OrderService", "OrderRequest", "NotificationService", "OrderRequest", channel="notify"),
        ],
        components=[
            Component(name="OrderService", requires=[_iref("PaymentRequest")], provides=[_iref("OrderRequest")]),
            Component(name="PaymentService", provides=[_iref("PaymentRequest")]),
            Component(name="NotificationService", requires=[_iref("OrderRequest")]),
        ],
    )
    out = _render(sys, tmp_path)
    assert out.exists()
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = _png_dimensions(out)
    assert w > 100
    assert h > 100
