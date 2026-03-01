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
# render_diagram — mocked diagrams
# ###############


def _make_diagrams_mock() -> tuple[MagicMock, MagicMock]:
    """Return (mock_diagrams_module, mock_diagrams_c4_module)."""
    mock_diagrams = MagicMock()
    mock_c4 = MagicMock()
    return mock_diagrams, mock_c4


def _diagrams_patch(mock_diagrams: MagicMock, mock_c4: MagicMock) -> ...:  # type: ignore[type-arg]
    return patch.dict(sys.modules, {"diagrams": mock_diagrams, "diagrams.c4": mock_c4})


def test_render_diagram_calls_diagrams(tmp_path: Path) -> None:
    """render_diagram imports diagrams and calls Diagram with the entity title."""
    mock_diagrams, mock_c4 = _make_diagrams_mock()
    data = DiagramData(title="SystemA", description="Test system")

    with _diagrams_patch(mock_diagrams, mock_c4):
        render_diagram(data, tmp_path / "out.png")

    mock_diagrams.Diagram.assert_called_once_with(
        "SystemA",
        filename=str(tmp_path / "out"),
        outformat="png",
        show=False,
    )


def test_render_diagram_adds_terminals(tmp_path: Path) -> None:
    """render_diagram creates a Person node for each terminal."""
    mock_diagrams, mock_c4 = _make_diagrams_mock()

    data = DiagramData(
        title="S",
        description=None,
        terminals=[
            InterfaceTerminal(name="Input", direction="in"),
            InterfaceTerminal(name="Output", direction="out"),
        ],
    )

    with _diagrams_patch(mock_diagrams, mock_c4):
        render_diagram(data, tmp_path / "out.png")

    calls = [str(c) for c in mock_c4.Person.call_args_list]
    assert any("Input" in c for c in calls)
    assert any("Output" in c for c in calls)


def test_render_diagram_adds_children(tmp_path: Path) -> None:
    """render_diagram creates a Container node for each child box."""
    mock_diagrams, mock_c4 = _make_diagrams_mock()

    data = DiagramData(
        title="S",
        description=None,
        children=[
            ChildBox(name="Alpha", description="first", kind="component"),
            ChildBox(name="Beta", description=None, kind="system"),
        ],
    )

    with _diagrams_patch(mock_diagrams, mock_c4):
        render_diagram(data, tmp_path / "out.png")

    assert mock_c4.Container.call_count == 2


def test_render_diagram_adds_connections(tmp_path: Path) -> None:
    """render_diagram creates an Edge for each connection."""
    mock_diagrams, mock_c4 = _make_diagrams_mock()

    data = DiagramData(
        title="S",
        description=None,
        children=[
            ChildBox(name="A", description=None, kind="component"),
            ChildBox(name="B", description=None, kind="component"),
        ],
        connections=[ConnectionData(source="A", target="B", label="IFace")],
    )

    with _diagrams_patch(mock_diagrams, mock_c4):
        render_diagram(data, tmp_path / "out.png")

    mock_diagrams.Edge.assert_called_once_with(label="IFace")


def test_render_diagram_uses_output_path(tmp_path: Path) -> None:
    """render_diagram passes the correct filename stem and format to Diagram."""
    mock_diagrams, mock_c4 = _make_diagrams_mock()

    out = tmp_path / "diagram.svg"
    data = DiagramData(title="S", description=None)

    with _diagrams_patch(mock_diagrams, mock_c4):
        render_diagram(data, out)

    mock_diagrams.Diagram.assert_called_once_with(
        "S",
        filename=str(tmp_path / "diagram"),
        outformat="svg",
        show=False,
    )


def test_render_diagram_raises_import_error_without_diagrams(tmp_path: Path) -> None:
    """render_diagram raises ImportError when diagrams is not installed."""
    data = DiagramData(title="S", description=None)
    # Setting diagrams to None in sys.modules makes `import diagrams` raise ImportError.
    with (
        patch.dict(sys.modules, {"diagrams": None}),  # type: ignore[dict-item]
        pytest.raises(ImportError),
    ):
        render_diagram(data, tmp_path / "out.png")
