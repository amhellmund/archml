# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for diagram data builder and renderer."""

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from archml.model.entities import (
    Component,
    Connection,
    ConnectionEndpoint,
    InterfaceRef,
    System,
)
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
# render_diagram — mocked pydiagrams
# ###############


def _make_pydiagrams_mock() -> MagicMock:
    """Return a mock pydiagrams module with ComponentDiagram."""
    mock_module = MagicMock(spec=ModuleType)
    mock_diagram = MagicMock()
    mock_module.ComponentDiagram.return_value = mock_diagram
    return mock_module


def test_render_diagram_calls_pydiagrams(tmp_path: Path) -> None:
    """render_diagram imports pydiagrams and calls ComponentDiagram."""
    mock_pydiagrams = _make_pydiagrams_mock()
    data = DiagramData(title="SystemA", description="Test system")

    with patch.dict(sys.modules, {"pydiagrams": mock_pydiagrams}):
        render_diagram(data, tmp_path / "out.png")

    mock_pydiagrams.ComponentDiagram.assert_called_once_with(
        title="SystemA", description="Test system"
    )


def test_render_diagram_adds_terminals(tmp_path: Path) -> None:
    """render_diagram calls add_interface for each terminal."""
    mock_pydiagrams = _make_pydiagrams_mock()
    mock_diag = mock_pydiagrams.ComponentDiagram.return_value

    data = DiagramData(
        title="S",
        description=None,
        terminals=[
            InterfaceTerminal(name="Input", direction="in"),
            InterfaceTerminal(name="Output", direction="out"),
        ],
    )

    with patch.dict(sys.modules, {"pydiagrams": mock_pydiagrams}):
        render_diagram(data, tmp_path / "out.png")

    calls = [str(c) for c in mock_diag.add_interface.call_args_list]
    assert any("Input" in c for c in calls)
    assert any("Output" in c for c in calls)


def test_render_diagram_adds_children(tmp_path: Path) -> None:
    """render_diagram calls add_component for each child box."""
    mock_pydiagrams = _make_pydiagrams_mock()
    mock_diag = mock_pydiagrams.ComponentDiagram.return_value

    data = DiagramData(
        title="S",
        description=None,
        children=[
            ChildBox(name="Alpha", description="first", kind="component"),
            ChildBox(name="Beta", description=None, kind="system"),
        ],
    )

    with patch.dict(sys.modules, {"pydiagrams": mock_pydiagrams}):
        render_diagram(data, tmp_path / "out.png")

    assert mock_diag.add_component.call_count == 2


def test_render_diagram_adds_connections(tmp_path: Path) -> None:
    """render_diagram calls add_connection for each connection."""
    mock_pydiagrams = _make_pydiagrams_mock()
    mock_diag = mock_pydiagrams.ComponentDiagram.return_value

    data = DiagramData(
        title="S",
        description=None,
        connections=[ConnectionData(source="A", target="B", label="IFace")],
    )

    with patch.dict(sys.modules, {"pydiagrams": mock_pydiagrams}):
        render_diagram(data, tmp_path / "out.png")

    mock_diag.add_connection.assert_called_once_with(source="A", target="B", label="IFace")


def test_render_diagram_calls_render_with_output_path(tmp_path: Path) -> None:
    """render_diagram calls diag.render() with the string output path."""
    mock_pydiagrams = _make_pydiagrams_mock()
    mock_diag = mock_pydiagrams.ComponentDiagram.return_value

    out = tmp_path / "diagram.svg"
    data = DiagramData(title="S", description=None)

    with patch.dict(sys.modules, {"pydiagrams": mock_pydiagrams}):
        render_diagram(data, out)

    mock_diag.render.assert_called_once_with(str(out))


def test_render_diagram_raises_import_error_without_pydiagrams(tmp_path: Path) -> None:
    """render_diagram raises ImportError when pydiagrams is not installed."""
    data = DiagramData(title="S", description=None)
    # Setting pydiagrams to None in sys.modules makes `import pydiagrams` raise ImportError.
    with patch.dict(sys.modules, {"pydiagrams": None}):  # type: ignore[dict-item]
        with pytest.raises(ImportError):
            render_diagram(data, tmp_path / "out.png")
