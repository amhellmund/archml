# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the static viewer JSON payload serialiser."""

from __future__ import annotations

import json

from archml.export import build_viewer_payload
from archml.model.entities import ArchFile, Component, System

# ###############
# Helpers
# ###############


def _files(**entities: Component | System) -> dict[str, ArchFile]:
    components = [e for e in entities.values() if isinstance(e, Component)]
    systems = [e for e in entities.values() if isinstance(e, System)]
    return {"main": ArchFile(components=components, systems=systems)}


def _parse(payload: str) -> dict:
    return json.loads(payload)


# ###############
# Tests
# ###############


# -------- output format --------


def test_output_is_valid_json() -> None:
    """build_viewer_payload always returns parseable JSON."""
    payload = build_viewer_payload({})
    _parse(payload)  # must not raise


def test_payload_version_field() -> None:
    """Payload carries a version field set to '1'."""
    data = _parse(build_viewer_payload({}))
    assert data["version"] == "1"


def test_payload_has_files_and_entities_keys() -> None:
    """Top-level keys are exactly version, files, and entities."""
    data = _parse(build_viewer_payload({}))
    assert set(data.keys()) == {"version", "files", "entities"}


def test_empty_workspace_produces_empty_collections() -> None:
    """An empty compiled dict yields empty files and entities."""
    data = _parse(build_viewer_payload({}))
    assert data["files"] == {}
    assert data["entities"] == []


# -------- files serialisation --------


def test_file_keys_preserved() -> None:
    """The canonical file keys are preserved in the files dict."""
    compiled = {
        "repo/services.archml": ArchFile(),
        "repo/ui.archml": ArchFile(),
    }
    data = _parse(build_viewer_payload(compiled))
    assert set(data["files"].keys()) == {"repo/services.archml", "repo/ui.archml"}


def test_full_arch_file_content_serialised() -> None:
    """ArchFile fields are included in each file entry."""
    comp = Component(name="Worker", title="Background Worker", qualified_name="Worker")
    compiled = {"f": ArchFile(components=[comp])}
    data = _parse(build_viewer_payload(compiled))
    file_data = data["files"]["f"]
    assert "components" in file_data
    assert file_data["components"][0]["name"] == "Worker"
    assert file_data["components"][0]["title"] == "Background Worker"


# -------- entity index --------


def test_top_level_system_in_index() -> None:
    """A top-level system appears in the entities index."""
    sys = System(name="OrderSys", qualified_name="OrderSys")
    data = _parse(build_viewer_payload(_files(OrderSys=sys)))
    qnames = [e["qualified_name"] for e in data["entities"]]
    assert "OrderSys" in qnames


def test_top_level_component_in_index() -> None:
    """A top-level component appears in the entities index."""
    comp = Component(name="Auth", qualified_name="Auth")
    data = _parse(build_viewer_payload(_files(Auth=comp)))
    qnames = [e["qualified_name"] for e in data["entities"]]
    assert "Auth" in qnames


def test_nested_component_in_system_included() -> None:
    """A component nested inside a system is included in the index."""
    child = Component(name="Cart", qualified_name="OrderSys::Cart")
    parent = System(name="OrderSys", qualified_name="OrderSys", components=[child])
    data = _parse(build_viewer_payload(_files(OrderSys=parent)))
    qnames = [e["qualified_name"] for e in data["entities"]]
    assert "OrderSys" in qnames
    assert "OrderSys::Cart" in qnames


def test_nested_subsystem_in_system_included() -> None:
    """A subsystem nested inside a system is included in the index."""
    sub = System(name="Payments", qualified_name="OrderSys::Payments")
    parent = System(name="OrderSys", qualified_name="OrderSys", systems=[sub])
    data = _parse(build_viewer_payload(_files(OrderSys=parent)))
    qnames = [e["qualified_name"] for e in data["entities"]]
    assert "OrderSys::Payments" in qnames


def test_deeply_nested_component_included() -> None:
    """Components nested multiple levels deep are all collected."""
    deep = Component(name="DB", qualified_name="Sys::Sub::DB")
    sub = System(name="Sub", qualified_name="Sys::Sub", components=[deep])
    root = System(name="Sys", qualified_name="Sys", systems=[sub])
    data = _parse(build_viewer_payload(_files(Sys=root)))
    qnames = [e["qualified_name"] for e in data["entities"]]
    assert "Sys" in qnames
    assert "Sys::Sub" in qnames
    assert "Sys::Sub::DB" in qnames


# -------- entity kind --------


def test_system_kind() -> None:
    """Normal systems have kind 'system'."""
    sys = System(name="S", qualified_name="S")
    data = _parse(build_viewer_payload(_files(S=sys)))
    entry = next(e for e in data["entities"] if e["qualified_name"] == "S")
    assert entry["kind"] == "system"


def test_external_system_kind() -> None:
    """External systems have kind 'external_system'."""
    sys = System(name="S", qualified_name="S", is_external=True)
    data = _parse(build_viewer_payload(_files(S=sys)))
    entry = next(e for e in data["entities"] if e["qualified_name"] == "S")
    assert entry["kind"] == "external_system"


def test_component_kind() -> None:
    """Normal components have kind 'component'."""
    comp = Component(name="C", qualified_name="C")
    data = _parse(build_viewer_payload(_files(C=comp)))
    entry = next(e for e in data["entities"] if e["qualified_name"] == "C")
    assert entry["kind"] == "component"


def test_external_component_kind() -> None:
    """External components have kind 'external_component'."""
    comp = Component(name="C", qualified_name="C", is_external=True)
    data = _parse(build_viewer_payload(_files(C=comp)))
    entry = next(e for e in data["entities"] if e["qualified_name"] == "C")
    assert entry["kind"] == "external_component"


# -------- entity metadata --------


def test_entity_title_included() -> None:
    """Entity title is included in the index entry."""
    sys = System(name="S", qualified_name="S", title="My System")
    data = _parse(build_viewer_payload(_files(S=sys)))
    entry = next(e for e in data["entities"] if e["qualified_name"] == "S")
    assert entry["title"] == "My System"


def test_entity_title_none_when_absent() -> None:
    """title is null in JSON when not set on the entity."""
    sys = System(name="S", qualified_name="S")
    data = _parse(build_viewer_payload(_files(S=sys)))
    entry = next(e for e in data["entities"] if e["qualified_name"] == "S")
    assert entry["title"] is None


def test_entity_file_key_matches() -> None:
    """Each entity entry carries the file_key of its owning ArchFile."""
    sys = System(name="S", qualified_name="S")
    compiled = {"services/main.archml": ArchFile(systems=[sys])}
    data = _parse(build_viewer_payload(compiled))
    entry = next(e for e in data["entities"] if e["qualified_name"] == "S")
    assert entry["file_key"] == "services/main.archml"


# -------- multi-file workspace --------


def test_entities_from_multiple_files_all_included() -> None:
    """Entities across multiple ArchFiles are all present in the index."""
    compiled = {
        "a.archml": ArchFile(systems=[System(name="A", qualified_name="A")]),
        "b.archml": ArchFile(components=[Component(name="B", qualified_name="B")]),
    }
    data = _parse(build_viewer_payload(compiled))
    qnames = [e["qualified_name"] for e in data["entities"]]
    assert "A" in qnames
    assert "B" in qnames


# -------- qualified_name fallback --------


def test_uses_name_when_qualified_name_empty() -> None:
    """Falls back to entity.name when qualified_name is empty string."""
    sys = System(name="Fallback", qualified_name="")
    data = _parse(build_viewer_payload(_files(Fallback=sys)))
    qnames = [e["qualified_name"] for e in data["entities"]]
    assert "Fallback" in qnames
