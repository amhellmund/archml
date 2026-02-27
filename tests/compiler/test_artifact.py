# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for ArchFile JSON serialization and deserialization (artifact.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from archml.compiler.artifact import (
    ARTIFACT_FORMAT_VERSION,
    deserialize,
    read_artifact,
    serialize,
    write_artifact,
)
from archml.model.entities import (
    ArchFile,
    Component,
    Connection,
    ConnectionEndpoint,
    EnumDef,
    ImportDeclaration,
    InterfaceDef,
    InterfaceRef,
    System,
    TypeDef,
)
from archml.model.types import (
    DirectoryTypeRef,
    Field,
    FileTypeRef,
    ListTypeRef,
    MapTypeRef,
    NamedTypeRef,
    OptionalTypeRef,
    PrimitiveType,
    PrimitiveTypeRef,
)

# ###############
# Helpers
# ###############


def _roundtrip(arch_file: ArchFile) -> ArchFile:
    """Serialize and immediately deserialize an ArchFile."""
    return deserialize(serialize(arch_file))


# ###############
# Tests: TypeRef serialization
# ###############


class TestTypeRefSerialization:
    """Each TypeRef variant must survive a serialize/deserialize roundtrip."""

    def test_primitive_string(self) -> None:
        f = Field(name="x", type=PrimitiveTypeRef(PrimitiveType.STRING))
        arch = ArchFile(types=[TypeDef(name="T", fields=[f])])
        result = _roundtrip(arch)
        field_type = result.types[0].fields[0].type
        assert isinstance(field_type, PrimitiveTypeRef)
        assert field_type.primitive == PrimitiveType.STRING

    def test_all_primitive_types(self) -> None:
        for prim in PrimitiveType:
            f = Field(name="x", type=PrimitiveTypeRef(prim))
            arch = ArchFile(types=[TypeDef(name="T", fields=[f])])
            result = _roundtrip(arch)
            field_type = result.types[0].fields[0].type
            assert isinstance(field_type, PrimitiveTypeRef)
            assert field_type.primitive == prim

    def test_file_type(self) -> None:
        f = Field(name="doc", type=FileTypeRef(), filetype="PDF")
        arch = ArchFile(interfaces=[InterfaceDef(name="I", fields=[f])])
        result = _roundtrip(arch)
        field_type = result.interfaces[0].fields[0].type
        assert isinstance(field_type, FileTypeRef)

    def test_directory_type(self) -> None:
        f = Field(name="artifacts", type=DirectoryTypeRef(), schema="Contains exports.")
        arch = ArchFile(interfaces=[InterfaceDef(name="I", fields=[f])])
        result = _roundtrip(arch)
        field_type = result.interfaces[0].fields[0].type
        assert isinstance(field_type, DirectoryTypeRef)

    def test_list_of_primitive(self) -> None:
        f = Field(name="ids", type=ListTypeRef(PrimitiveTypeRef(PrimitiveType.STRING)))
        arch = ArchFile(types=[TypeDef(name="T", fields=[f])])
        result = _roundtrip(arch)
        field_type = result.types[0].fields[0].type
        assert isinstance(field_type, ListTypeRef)
        assert isinstance(field_type.element_type, PrimitiveTypeRef)
        assert field_type.element_type.primitive == PrimitiveType.STRING

    def test_map_type(self) -> None:
        f = Field(
            name="mapping",
            type=MapTypeRef(PrimitiveTypeRef(PrimitiveType.STRING), PrimitiveTypeRef(PrimitiveType.INT)),
        )
        arch = ArchFile(types=[TypeDef(name="T", fields=[f])])
        result = _roundtrip(arch)
        field_type = result.types[0].fields[0].type
        assert isinstance(field_type, MapTypeRef)
        assert isinstance(field_type.key_type, PrimitiveTypeRef)
        assert field_type.key_type.primitive == PrimitiveType.STRING
        assert isinstance(field_type.value_type, PrimitiveTypeRef)
        assert field_type.value_type.primitive == PrimitiveType.INT

    def test_optional_named_type(self) -> None:
        f = Field(name="meta", type=OptionalTypeRef(NamedTypeRef("Metadata")))
        arch = ArchFile(types=[TypeDef(name="T", fields=[f])])
        result = _roundtrip(arch)
        field_type = result.types[0].fields[0].type
        assert isinstance(field_type, OptionalTypeRef)
        assert isinstance(field_type.inner_type, NamedTypeRef)
        assert field_type.inner_type.name == "Metadata"

    def test_named_type(self) -> None:
        f = Field(name="status", type=NamedTypeRef("OrderStatus"))
        arch = ArchFile(types=[TypeDef(name="T", fields=[f])])
        result = _roundtrip(arch)
        field_type = result.types[0].fields[0].type
        assert isinstance(field_type, NamedTypeRef)
        assert field_type.name == "OrderStatus"

    def test_nested_list_of_map(self) -> None:
        inner = MapTypeRef(PrimitiveTypeRef(PrimitiveType.STRING), PrimitiveTypeRef(PrimitiveType.INT))
        f = Field(name="data", type=ListTypeRef(inner))
        arch = ArchFile(types=[TypeDef(name="T", fields=[f])])
        result = _roundtrip(arch)
        field_type = result.types[0].fields[0].type
        assert isinstance(field_type, ListTypeRef)
        assert isinstance(field_type.element_type, MapTypeRef)


# ###############
# Tests: Entity serialization
# ###############


class TestEnumSerialization:
    def test_minimal_enum(self) -> None:
        enum = EnumDef(name="Status", values=["Active", "Inactive"])
        arch = ArchFile(enums=[enum])
        result = _roundtrip(arch)
        assert len(result.enums) == 1
        e = result.enums[0]
        assert e.name == "Status"
        assert e.values == ["Active", "Inactive"]
        assert e.title is None
        assert e.description is None
        assert e.tags == []

    def test_full_enum(self) -> None:
        enum = EnumDef(
            name="Color",
            values=["Red", "Green", "Blue"],
            title="Primary Colors",
            description="The three primary colors.",
            tags=["ui"],
        )
        arch = ArchFile(enums=[enum])
        result = _roundtrip(arch)
        e = result.enums[0]
        assert e.title == "Primary Colors"
        assert e.description == "The three primary colors."
        assert e.tags == ["ui"]


class TestTypeSerialization:
    def test_type_with_fields(self) -> None:
        type_def = TypeDef(
            name="Address",
            fields=[
                Field(name="street", type=PrimitiveTypeRef(PrimitiveType.STRING), description="Street name"),
                Field(name="zip", type=PrimitiveTypeRef(PrimitiveType.INT)),
            ],
            title="Postal Address",
            tags=["common"],
        )
        arch = ArchFile(types=[type_def])
        result = _roundtrip(arch)
        assert len(result.types) == 1
        t = result.types[0]
        assert t.name == "Address"
        assert t.title == "Postal Address"
        assert len(t.fields) == 2
        assert t.fields[0].name == "street"
        assert t.fields[0].description == "Street name"
        assert t.fields[1].name == "zip"


class TestInterfaceSerialization:
    def test_versioned_interface(self) -> None:
        iface = InterfaceDef(
            name="OrderRequest",
            version="v2",
            fields=[Field(name="order_id", type=PrimitiveTypeRef(PrimitiveType.STRING))],
        )
        arch = ArchFile(interfaces=[iface])
        result = _roundtrip(arch)
        i = result.interfaces[0]
        assert i.name == "OrderRequest"
        assert i.version == "v2"

    def test_interface_without_version(self) -> None:
        iface = InterfaceDef(name="Ping", fields=[])
        arch = ArchFile(interfaces=[iface])
        result = _roundtrip(arch)
        assert result.interfaces[0].version is None


class TestComponentSerialization:
    def test_minimal_component(self) -> None:
        comp = Component(name="Worker")
        arch = ArchFile(components=[comp])
        result = _roundtrip(arch)
        assert len(result.components) == 1
        c = result.components[0]
        assert c.name == "Worker"
        assert c.is_external is False
        assert c.requires == []
        assert c.provides == []

    def test_external_component(self) -> None:
        comp = Component(name="Stripe", is_external=True)
        arch = ArchFile(components=[comp])
        result = _roundtrip(arch)
        assert result.components[0].is_external is True

    def test_component_with_interface_refs(self) -> None:
        comp = Component(
            name="OrderService",
            requires=[InterfaceRef(name="OrderRequest", version="v2")],
            provides=[InterfaceRef(name="OrderConfirmation")],
        )
        arch = ArchFile(components=[comp])
        result = _roundtrip(arch)
        c = result.components[0]
        assert len(c.requires) == 1
        assert c.requires[0].name == "OrderRequest"
        assert c.requires[0].version == "v2"
        assert len(c.provides) == 1
        assert c.provides[0].name == "OrderConfirmation"
        assert c.provides[0].version is None

    def test_nested_components(self) -> None:
        inner = Component(name="Inner", provides=[InterfaceRef(name="Signal")])
        outer = Component(
            name="Outer",
            components=[inner],
            connections=[
                Connection(
                    source=ConnectionEndpoint(entity="Inner"),
                    target=ConnectionEndpoint(entity="Sink"),
                    interface=InterfaceRef(name="Signal"),
                    is_async=True,
                    protocol="gRPC",
                )
            ],
        )
        arch = ArchFile(components=[outer])
        result = _roundtrip(arch)
        c = result.components[0]
        assert len(c.components) == 1
        assert c.components[0].name == "Inner"
        assert len(c.connections) == 1
        conn = c.connections[0]
        assert conn.source.entity == "Inner"
        assert conn.target.entity == "Sink"
        assert conn.interface.name == "Signal"
        assert conn.is_async is True
        assert conn.protocol == "gRPC"


class TestSystemSerialization:
    def test_system_with_nested_systems(self) -> None:
        inner_sys = System(name="SubSystem")
        outer_sys = System(
            name="OuterSystem",
            title="Top-level system",
            systems=[inner_sys],
            tags=["top"],
        )
        arch = ArchFile(systems=[outer_sys])
        result = _roundtrip(arch)
        s = result.systems[0]
        assert s.name == "OuterSystem"
        assert s.title == "Top-level system"
        assert s.tags == ["top"]
        assert len(s.systems) == 1
        assert s.systems[0].name == "SubSystem"


class TestImportSerialization:
    def test_import_declaration(self) -> None:
        imp = ImportDeclaration(source_path="imports/types", entities=["OrderRequest", "PaymentRequest"])
        arch = ArchFile(imports=[imp])
        result = _roundtrip(arch)
        assert len(result.imports) == 1
        i = result.imports[0]
        assert i.source_path == "imports/types"
        assert i.entities == ["OrderRequest", "PaymentRequest"]


# ###############
# Tests: Minimal empty ArchFile
# ###############


class TestEmptyArchFile:
    def test_empty_arch_file_roundtrip(self) -> None:
        arch = ArchFile()
        result = _roundtrip(arch)
        assert result.imports == []
        assert result.enums == []
        assert result.types == []
        assert result.interfaces == []
        assert result.components == []
        assert result.systems == []

    def test_json_contains_version(self) -> None:
        arch = ArchFile()
        data = serialize(arch)
        obj = json.loads(data)
        assert obj["v"] == ARTIFACT_FORMAT_VERSION

    def test_compact_json_no_whitespace(self) -> None:
        arch = ArchFile()
        data = serialize(arch)
        # Compact JSON should not contain newlines or indentation
        assert "\n" not in data
        assert "  " not in data


# ###############
# Tests: File I/O
# ###############


class TestArtifactFileIO:
    def test_write_and_read_artifact(self, tmp_path: Path) -> None:
        arch = ArchFile(enums=[EnumDef(name="Status", values=["A", "B"])])
        artifact_path = tmp_path / "status.json"
        write_artifact(arch, artifact_path)
        assert artifact_path.exists()
        loaded = read_artifact(artifact_path)
        assert loaded.enums[0].name == "Status"
        assert loaded.enums[0].values == ["A", "B"]

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        arch = ArchFile()
        artifact_path = tmp_path / "deep" / "nested" / "artifact.json"
        write_artifact(arch, artifact_path)
        assert artifact_path.exists()

    def test_deserialize_wrong_version_raises(self) -> None:
        data = json.dumps({"v": "999", "imports": [], "enums": [], "types": [], "interfaces": [], "components": [], "systems": []})
        with pytest.raises(ValueError, match="Unsupported artifact format version"):
            deserialize(data)
