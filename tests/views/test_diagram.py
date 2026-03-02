# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for diagram data builder and renderer."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from archml.model.entities import Component, Connection, ConnectionEndpoint, InterfaceRef, System
from archml.views.diagram import (
    ChildBox,
    ConnectionData,
    DiagramData,
    InterfaceTerminal,
    build_diagram_data,
    render_diagram,
)

# ###############
# Helpers
# ###############


def _iref(name: str, version: str | None = None) -> InterfaceRef:
    return InterfaceRef(name=name, version=version)


def _conn(source: str, target: str, interface: str) -> Connection:
    return Connection(
        source=ConnectionEndpoint(entity=source),
        target=ConnectionEndpoint(entity=target),
        interface=InterfaceRef(name=interface),
    )


# ###############
# build_diagram_data — title and description
# ###############


def test_build_title_from_component() -> None:
    """Diagram title is the component name."""
    comp = Component(name="Worker")
    data = build_diagram_data(comp)
    assert data.title == "Worker"


def test_build_title_from_system() -> None:
    """Diagram title is the system name."""
    sys_a = System(name="SystemA")
    data = build_diagram_data(sys_a)
    assert data.title == "SystemA"


def test_build_description_propagated() -> None:
    """Description is forwarded to DiagramData."""
    comp = Component(name="Worker", description="Does the work")
    data = build_diagram_data(comp)
    assert data.description == "Does the work"


def test_build_description_none_when_absent() -> None:
    """Description is None when the entity has no description."""
    comp = Component(name="Worker")
    data = build_diagram_data(comp)
    assert data.description is None


# ###############
# build_diagram_data — children
# ###############


def test_build_children_from_component_with_sub_components() -> None:
    """Sub-components are listed as ChildBox entries with kind='component'."""
    child_a = Component(name="Alpha", description="First")
    child_b = Component(name="Beta")
    parent = Component(name="Parent", components=[child_a, child_b])
    data = build_diagram_data(parent)
    assert data.children == [
        ChildBox(name="Alpha", description="First", kind="component"),
        ChildBox(name="Beta", description=None, kind="component"),
    ]


def test_build_children_from_system_includes_components_and_subsystems() -> None:
    """System children include both components and sub-systems."""
    comp = Component(name="Worker")
    sub = System(name="SubSys")
    parent = System(name="Root", components=[comp], systems=[sub])
    data = build_diagram_data(parent)
    names_kinds = [(c.name, c.kind) for c in data.children]
    assert ("Worker", "component") in names_kinds
    assert ("SubSys", "system") in names_kinds


def test_build_no_children_for_leaf() -> None:
    """A leaf entity (no sub-components or sub-systems) produces no children."""
    comp = Component(name="Leaf")
    data = build_diagram_data(comp)
    assert data.children == []


# ###############
# build_diagram_data — terminals
# ###############


def test_build_requires_terminals() -> None:
    """Requires interfaces appear as incoming terminals."""
    comp = Component(name="C", requires=[_iref("DataFeed")])
    data = build_diagram_data(comp)
    assert InterfaceTerminal(name="DataFeed", direction="in") in data.terminals


def test_build_provides_terminals() -> None:
    """Provides interfaces appear as outgoing terminals."""
    comp = Component(name="C", provides=[_iref("Result")])
    data = build_diagram_data(comp)
    assert InterfaceTerminal(name="Result", direction="out") in data.terminals


def test_build_versioned_interface_terminal() -> None:
    """Versioned interfaces include the version suffix in their label."""
    comp = Component(name="C", provides=[_iref("API", version="v2")])
    data = build_diagram_data(comp)
    assert InterfaceTerminal(name="API@v2", direction="out") in data.terminals


def test_build_no_terminals_for_leaf() -> None:
    """An entity with no requires or provides has no terminals."""
    comp = Component(name="Isolated")
    data = build_diagram_data(comp)
    assert data.terminals == []


# ###############
# build_diagram_data — connections
# ###############


def test_build_connections() -> None:
    """Connections are translated to ConnectionData entries."""
    child_a = Component(name="A")
    child_b = Component(name="B")
    conn = _conn("A", "B", "IFace")
    parent = Component(name="Parent", components=[child_a, child_b], connections=[conn])
    data = build_diagram_data(parent)
    assert ConnectionData(source="A", target="B", label="IFace") in data.connections


def test_build_no_connections_for_leaf() -> None:
    """A leaf entity has no connections."""
    comp = Component(name="Leaf")
    data = build_diagram_data(comp)
    assert data.connections == []


# ###############
# render_diagram — mock infrastructure
# ###############


class _NodeStub:
    """Minimal stub for diagrams.Node that supports subclassing and tracks labels."""

    _icon_dir = None
    _icon = None
    _height = 1.9
    _attr: dict[str, str] = {}

    # Collects labels of every instance created; reset via the autouse fixture.
    created_labels: list[str] = []

    def __init__(self, label: str = "", **attrs: object) -> None:
        _NodeStub.created_labels.append(label)

    def __rshift__(self, other: object) -> object:
        return other

    def __lshift__(self, other: object) -> object:
        return other


@pytest.fixture(autouse=True)
def _reset_node_stub() -> None:
    """Clear _NodeStub tracking before every test."""
    _NodeStub.created_labels.clear()


def _make_diagrams_mock() -> MagicMock:
    """Return a mock diagrams module with a proper Node stub class."""
    mock = MagicMock()
    mock.Node = _NodeStub
    return mock


def _diagrams_patch(mock_diagrams: MagicMock) -> ...:  # type: ignore[type-arg]
    return patch.dict(sys.modules, {"diagrams": mock_diagrams})


# ###############
# render_diagram — Diagram construction
# ###############


def test_render_diagram_calls_diagram_with_title(tmp_path: Path) -> None:
    """render_diagram creates a Diagram context with the entity title."""
    mock = _make_diagrams_mock()
    data = DiagramData(title="SystemA", description=None)

    with _diagrams_patch(mock):
        render_diagram(data, tmp_path / "out.png")

    mock.Diagram.assert_called_once_with(
        "SystemA",
        filename=str(tmp_path / "out"),
        outformat="png",
        show=False,
        direction="LR",
    )


def test_render_diagram_svg_format_from_extension(tmp_path: Path) -> None:
    """The output format is derived from the path extension."""
    mock = _make_diagrams_mock()
    data = DiagramData(title="S", description=None)

    with _diagrams_patch(mock):
        render_diagram(data, tmp_path / "diagram.svg")

    _, kwargs = mock.Diagram.call_args
    assert kwargs["outformat"] == "svg"


def test_render_diagram_default_format_is_svg(tmp_path: Path) -> None:
    """When the path has no extension the format defaults to svg."""
    mock = _make_diagrams_mock()
    data = DiagramData(title="S", description=None)

    with _diagrams_patch(mock):
        render_diagram(data, tmp_path / "out")

    _, kwargs = mock.Diagram.call_args
    assert kwargs["outformat"] == "svg"


# ###############
# render_diagram — terminal nodes
# ###############


def test_render_diagram_creates_node_for_requires_terminal(tmp_path: Path) -> None:
    """A _TerminalNode is instantiated for each requires interface."""
    mock = _make_diagrams_mock()
    data = DiagramData(
        title="S",
        description=None,
        terminals=[InterfaceTerminal(name="DataFeed", direction="in")],
    )

    with _diagrams_patch(mock):
        render_diagram(data, tmp_path / "out.svg")

    assert "DataFeed" in _NodeStub.created_labels


def test_render_diagram_creates_node_for_provides_terminal(tmp_path: Path) -> None:
    """A _TerminalNode is instantiated for each provides interface."""
    mock = _make_diagrams_mock()
    data = DiagramData(
        title="S",
        description=None,
        terminals=[InterfaceTerminal(name="Result", direction="out")],
    )

    with _diagrams_patch(mock):
        render_diagram(data, tmp_path / "out.svg")

    assert "Result" in _NodeStub.created_labels


def test_render_diagram_creates_nodes_for_both_terminals(tmp_path: Path) -> None:
    """Terminal nodes are created for both requires and provides interfaces."""
    mock = _make_diagrams_mock()
    data = DiagramData(
        title="S",
        description=None,
        terminals=[
            InterfaceTerminal(name="In", direction="in"),
            InterfaceTerminal(name="Out", direction="out"),
        ],
    )

    with _diagrams_patch(mock):
        render_diagram(data, tmp_path / "out.svg")

    assert "In" in _NodeStub.created_labels
    assert "Out" in _NodeStub.created_labels


# ###############
# render_diagram — leaf vs cluster
# ###############


def test_render_diagram_uses_entity_node_for_leaf(tmp_path: Path) -> None:
    """A leaf entity (no children) creates a single entity node."""
    mock = _make_diagrams_mock()
    data = DiagramData(title="Leaf", description=None)

    with _diagrams_patch(mock):
        render_diagram(data, tmp_path / "out.svg")

    # No Cluster for leaf entities
    mock.Cluster.assert_not_called()
    # The entity title appears as a node label
    assert "Leaf" in _NodeStub.created_labels


def test_render_diagram_uses_cluster_for_entity_with_children(tmp_path: Path) -> None:
    """An entity with children wraps them in a Cluster."""
    mock = _make_diagrams_mock()
    data = DiagramData(
        title="Parent",
        description=None,
        children=[ChildBox(name="Alpha", description=None, kind="component")],
    )

    with _diagrams_patch(mock):
        render_diagram(data, tmp_path / "out.svg")

    mock.Cluster.assert_called_once_with("Parent")


def test_render_diagram_creates_child_nodes(tmp_path: Path) -> None:
    """A node is instantiated for each child inside the cluster."""
    mock = _make_diagrams_mock()
    data = DiagramData(
        title="S",
        description=None,
        children=[
            ChildBox(name="Alpha", description=None, kind="component"),
            ChildBox(name="Beta", description=None, kind="system"),
        ],
    )

    with _diagrams_patch(mock):
        render_diagram(data, tmp_path / "out.svg")

    assert "Alpha" in _NodeStub.created_labels
    assert "Beta" in _NodeStub.created_labels


# ###############
# render_diagram — connections
# ###############


def test_render_diagram_creates_edge_for_child_connection(tmp_path: Path) -> None:
    """An Edge is created for each connection between children."""
    mock = _make_diagrams_mock()
    data = DiagramData(
        title="S",
        description=None,
        children=[
            ChildBox(name="A", description=None, kind="component"),
            ChildBox(name="B", description=None, kind="component"),
        ],
        connections=[ConnectionData(source="A", target="B", label="IFace")],
    )

    with _diagrams_patch(mock):
        render_diagram(data, tmp_path / "out.svg")

    mock.Edge.assert_called_with(label="IFace")


def test_render_diagram_creates_edges_for_terminals(tmp_path: Path) -> None:
    """Edges are created to connect terminal nodes to the entity."""
    mock = _make_diagrams_mock()
    data = DiagramData(
        title="S",
        description=None,
        terminals=[
            InterfaceTerminal(name="In", direction="in"),
            InterfaceTerminal(name="Out", direction="out"),
        ],
    )

    with _diagrams_patch(mock):
        render_diagram(data, tmp_path / "out.svg")

    # Edge() (no label) is called for each terminal connection
    assert mock.Edge.called


# ###############
# render_diagram — ImportError
# ###############


def test_render_diagram_raises_import_error_without_diagrams(tmp_path: Path) -> None:
    """render_diagram raises ImportError when the diagrams package is missing."""
    data = DiagramData(title="S", description=None)
    with (
        patch.dict(sys.modules, {"diagrams": None}),  # type: ignore[dict-item]
        pytest.raises(ImportError),
    ):
        render_diagram(data, tmp_path / "out.png")
