# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Golden-file tests: Python _build_dot output must match committed .dot snapshots.

Run ``UPDATE_SNAPSHOTS=1 uv run pytest tests/views/test_dot_sync.py`` to
regenerate snapshot files after intentional changes to _build_dot.  This also
rewrites the .viz.json fixtures consumed by the JavaScript test suite
(dot.test.ts), keeping both sides in sync.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

import pytest

from archml.model.entities import Component, ConnectDef, ExposeDef, InterfaceRef
from archml.views.layout import _build_dot
from archml.views.placement import LayoutConfig
from archml.views.topology import VizBoundary, VizDiagram, VizEdge, VizNode, VizPort, build_viz_diagram

_FIXTURES_DIR = Path(__file__).parent.parent / "dot_sync"

# ###############
# Public Interface
# ###############


@pytest.fixture(scope="session")
def snapshot_update() -> bool:
    """Return True when UPDATE_SNAPSHOTS=1 is set in the environment."""
    return os.environ.get("UPDATE_SNAPSHOTS") == "1"


def test_flat_dot_matches_snapshot(snapshot_update: bool) -> None:
    """Flat component: two child nodes, one intra-cluster edge (minlen=1)."""
    _check_dot_snapshot("flat", _build_flat(), snapshot_update)


def test_with_terminals_dot_matches_snapshot(snapshot_update: bool) -> None:
    """Component with expose: peripheral terminal nodes and edges (minlen=3)."""
    _check_dot_snapshot("with_terminals", _build_with_terminals(), snapshot_update)


def test_nested_dot_matches_snapshot(snapshot_update: bool) -> None:
    """Two nested boundaries with a cross-cluster edge (minlen=2)."""
    _check_dot_snapshot("nested", _build_nested(), snapshot_update)


# ################
# Implementation
# ################


def _check_dot_snapshot(name: str, diagram: VizDiagram, update: bool) -> None:
    """Compare _build_dot output against a committed snapshot file.

    When *update* is True, rewrite the snapshot and the companion .viz.json
    fixture (consumed by the JS golden-file test) instead of comparing.
    """
    actual = _build_dot(diagram, LayoutConfig())
    snap_path = _FIXTURES_DIR / f"{name}.dot"
    viz_path = _FIXTURES_DIR / f"{name}.viz.json"

    if update:
        _FIXTURES_DIR.mkdir(exist_ok=True)
        snap_path.write_text(actual, encoding="utf-8")
        viz_path.write_text(
            json.dumps(dataclasses.asdict(diagram), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return

    if not snap_path.exists():
        pytest.fail(
            f"Snapshot '{snap_path.name}' not found. "
            "Run UPDATE_SNAPSHOTS=1 uv run pytest tests/views/test_dot_sync.py to generate."
        )

    expected = snap_path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"DOT output for '{name}' has drifted from snapshot.\n"
        "Run UPDATE_SNAPSHOTS=1 uv run pytest tests/views/test_dot_sync.py to regenerate."
    )


def _iref(name: str) -> InterfaceRef:
    return InterfaceRef(name=name)


def _build_flat() -> VizDiagram:
    """Component 'Svc' with two child components connected directly."""
    alpha = Component(name="Alpha", provides=[_iref("IFace")])
    beta = Component(name="Beta", requires=[_iref("IFace")])
    svc = Component(
        name="Svc",
        components=[alpha, beta],
        connects=[ConnectDef(src_entity="Alpha", src_port="IFace", dst_entity="Beta", dst_port="IFace")],
    )
    return build_viz_diagram(svc)


def _build_with_terminals() -> VizDiagram:
    """Component 'Api' exposes a child interface, producing a peripheral terminal."""
    worker = Component(name="Worker", provides=[_iref("Response")])
    api = Component(
        name="Api",
        components=[worker],
        exposes=[ExposeDef(entity="Worker", port="Response")],
    )
    return build_viz_diagram(api)


def _build_nested() -> VizDiagram:
    """Two nested system boundaries with a cross-cluster edge (minlen=2).

    Built directly from VizDiagram dataclasses to exercise the DOT generator
    with nested cluster structure without depending on topology builder details.

        App (root boundary)
          Front (inner boundary)
            Ui  (provides IFace)
          Back  (inner boundary)
            Api  (requires IFace)
          edge: Ui.prov.IFace → Api.req.IFace
    """
    ui_port = VizPort(
        id="App__Front__Ui.prov.IFace",
        node_id="App__Front__Ui",
        interface_name="IFace",
        direction="provides",
    )
    api_port = VizPort(
        id="App__Back__Api.req.IFace",
        node_id="App__Back__Api",
        interface_name="IFace",
        direction="requires",
    )
    ui = VizNode(
        id="App__Front__Ui",
        label="Ui",
        title=None,
        kind="component",
        entity_path="App::Front::Ui",
        ports=[ui_port],
    )
    api_node = VizNode(
        id="App__Back__Api",
        label="Api",
        title=None,
        kind="component",
        entity_path="App::Back::Api",
        ports=[api_port],
    )
    front = VizBoundary(
        id="App__Front",
        label="Front",
        title=None,
        kind="system",
        entity_path="App::Front",
        children=[ui],
    )
    back = VizBoundary(
        id="App__Back",
        label="Back",
        title=None,
        kind="system",
        entity_path="App::Back",
        children=[api_node],
    )
    root = VizBoundary(
        id="App",
        label="App",
        title=None,
        kind="system",
        entity_path="App",
        children=[front, back],
    )
    edge = VizEdge(
        id="edge.App__Front__Ui.prov.IFace--App__Back__Api.req.IFace",
        source_port_id="App__Front__Ui.prov.IFace",
        target_port_id="App__Back__Api.req.IFace",
        label="IFace",
        interface_name="IFace",
    )
    return VizDiagram(
        id="diagram.App",
        title="App",
        description=None,
        root=root,
        peripheral_nodes=[],
        edges=[edge],
    )
