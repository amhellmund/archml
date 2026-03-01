# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the entity path resolver."""

import pytest

from archml.model.entities import ArchFile, Component, System
from archml.views.resolver import EntityNotFoundError, resolve_entity

# ###############
# Public Interface
# ###############


def _make_files(**entities: Component | System) -> dict[str, ArchFile]:
    """Build a minimal arch_files dict with the given top-level entities."""
    components = [e for e in entities.values() if isinstance(e, Component)]
    systems = [e for e in entities.values() if isinstance(e, System)]
    return {"main": ArchFile(components=components, systems=systems)}


# -------- top-level resolution --------


def test_resolve_top_level_system() -> None:
    """Resolving a bare system name returns that system."""
    sys_a = System(name="SystemA")
    files = _make_files(SystemA=sys_a)
    result = resolve_entity(files, "SystemA")
    assert result is sys_a


def test_resolve_top_level_component() -> None:
    """Resolving a bare component name returns that component."""
    comp = Component(name="Worker")
    files = _make_files(Worker=comp)
    result = resolve_entity(files, "Worker")
    assert result is comp


def test_resolve_top_level_system_across_multiple_files() -> None:
    """Entity is found when it lives in the second of two arch files."""
    comp = Component(name="Auth")
    files = {
        "file_a": ArchFile(components=[Component(name="Other")]),
        "file_b": ArchFile(components=[comp]),
    }
    result = resolve_entity(files, "Auth")
    assert result is comp


# -------- nested resolution --------


def test_resolve_nested_component_in_system() -> None:
    """Resolving 'SystemA::Worker' returns the Worker component inside SystemA."""
    worker = Component(name="Worker")
    sys_a = System(name="SystemA", components=[worker])
    files = _make_files(SystemA=sys_a)
    result = resolve_entity(files, "SystemA::Worker")
    assert result is worker


def test_resolve_three_level_path() -> None:
    """Resolving 'SystemA::Sub::Leaf' navigates two levels deep."""
    leaf = Component(name="Leaf")
    sub = Component(name="Sub", components=[leaf])
    sys_a = System(name="SystemA", components=[sub])
    files = _make_files(SystemA=sys_a)
    result = resolve_entity(files, "SystemA::Sub::Leaf")
    assert result is leaf


def test_resolve_nested_system_in_system() -> None:
    """Resolving 'Outer::Inner' where Inner is a sub-system."""
    inner = System(name="Inner")
    outer = System(name="Outer", systems=[inner])
    files = _make_files(Outer=outer)
    result = resolve_entity(files, "Outer::Inner")
    assert result is inner


def test_resolve_component_in_nested_system() -> None:
    """Component inside a nested system is reachable via multi-segment path."""
    comp = Component(name="Worker")
    inner = System(name="Inner", components=[comp])
    outer = System(name="Outer", systems=[inner])
    files = _make_files(Outer=outer)
    result = resolve_entity(files, "Outer::Inner::Worker")
    assert result is comp


# -------- whitespace tolerance --------


def test_resolve_path_with_spaces_around_separator() -> None:
    """Segments are stripped of surrounding whitespace."""
    worker = Component(name="Worker")
    sys_a = System(name="SystemA", components=[worker])
    files = _make_files(SystemA=sys_a)
    result = resolve_entity(files, " SystemA :: Worker ")
    assert result is worker


# -------- error cases --------


def test_resolve_unknown_top_level_raises() -> None:
    """An unknown top-level name raises EntityNotFoundError."""
    files = _make_files(Foo=Component(name="Foo"))
    with pytest.raises(EntityNotFoundError, match="Bar"):
        resolve_entity(files, "Bar")


def test_resolve_unknown_child_raises() -> None:
    """An unknown child segment raises EntityNotFoundError."""
    sys_a = System(name="SystemA", components=[Component(name="Worker")])
    files = _make_files(SystemA=sys_a)
    with pytest.raises(EntityNotFoundError, match="Missing"):
        resolve_entity(files, "SystemA::Missing")


def test_resolve_empty_path_raises() -> None:
    """An empty path string raises EntityNotFoundError."""
    files: dict[str, ArchFile] = {}
    with pytest.raises(EntityNotFoundError):
        resolve_entity(files, "")


def test_resolve_empty_files_raises() -> None:
    """Raises EntityNotFoundError when arch_files is empty."""
    with pytest.raises(EntityNotFoundError):
        resolve_entity({}, "SystemA")
