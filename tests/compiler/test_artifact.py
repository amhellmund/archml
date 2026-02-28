# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ArchML compiler artifact serialization."""

from pathlib import Path

import pytest

from archml.compiler.artifact import deserialize, read_artifact, serialize, write_artifact
from archml.compiler.parser import parse
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
    FieldDef,
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
    """Serialize and deserialize an ArchFile."""
    return deserialize(serialize(arch_file))


def _roundtrip_file(arch_file: ArchFile, tmp_path: Path) -> ArchFile:
    """Write and read an ArchFile artifact."""
    path = tmp_path / "test.archml.json"
    write_artifact(arch_file, path)
    return read_artifact(path)


# ###############
# Serialize / Deserialize: ArchFile structure
# ###############


class TestEmptyArchFile:
    def test_empty_roundtrip(self) -> None:
        af = ArchFile()
        result = _roundtrip(af)
        assert result == af

    def test_json_is_a_string(self) -> None:
        af = ArchFile()
        json_str = serialize(af)
        assert isinstance(json_str, str)
        assert len(json_str) > 0


class TestPrimitiveTypeRefs:
    """All PrimitiveType variants survive serialization roundtrip."""

    @pytest.mark.parametrize(
        "primitive",
        [
            PrimitiveType.STRING,
            PrimitiveType.INT,
            PrimitiveType.FLOAT,
            PrimitiveType.DECIMAL,
            PrimitiveType.BOOL,
            PrimitiveType.BYTES,
            PrimitiveType.TIMESTAMP,
            PrimitiveType.DATETIME,
        ],
    )
    def test_primitive_ref_roundtrip(self, primitive: PrimitiveType) -> None:
        af = ArchFile(
            types=[
                TypeDef(
                    name="T",
                    fields=[FieldDef(name="f", type=PrimitiveTypeRef(primitive=primitive))],
                )
            ]
        )
        result = _roundtrip(af)
        assert result.types[0].fields[0].type == PrimitiveTypeRef(primitive=primitive)


class TestContainerTypeRefs:
    def test_list_type_ref(self) -> None:
        af = ArchFile(
            types=[
                TypeDef(
                    name="T",
                    fields=[
                        FieldDef(
                            name="items",
                            type=ListTypeRef(element_type=PrimitiveTypeRef(primitive=PrimitiveType.STRING)),
                        )
                    ],
                )
            ]
        )
        result = _roundtrip(af)
        field_type = result.types[0].fields[0].type
        assert isinstance(field_type, ListTypeRef)
        assert isinstance(field_type.element_type, PrimitiveTypeRef)
        assert field_type.element_type.primitive == PrimitiveType.STRING

    def test_map_type_ref(self) -> None:
        af = ArchFile(
            types=[
                TypeDef(
                    name="T",
                    fields=[
                        FieldDef(
                            name="mapping",
                            type=MapTypeRef(
                                key_type=PrimitiveTypeRef(primitive=PrimitiveType.STRING),
                                value_type=PrimitiveTypeRef(primitive=PrimitiveType.INT),
                            ),
                        )
                    ],
                )
            ]
        )
        result = _roundtrip(af)
        field_type = result.types[0].fields[0].type
        assert isinstance(field_type, MapTypeRef)
        assert isinstance(field_type.key_type, PrimitiveTypeRef)
        assert isinstance(field_type.value_type, PrimitiveTypeRef)

    def test_optional_type_ref(self) -> None:
        af = ArchFile(
            types=[
                TypeDef(
                    name="T",
                    fields=[
                        FieldDef(
                            name="opt",
                            type=OptionalTypeRef(inner_type=PrimitiveTypeRef(primitive=PrimitiveType.STRING)),
                        )
                    ],
                )
            ]
        )
        result = _roundtrip(af)
        field_type = result.types[0].fields[0].type
        assert isinstance(field_type, OptionalTypeRef)
        assert isinstance(field_type.inner_type, PrimitiveTypeRef)

    def test_file_type_ref(self) -> None:
        af = ArchFile(interfaces=[InterfaceDef(name="I", fields=[FieldDef(name="f", type=FileTypeRef())])])
        result = _roundtrip(af)
        assert isinstance(result.interfaces[0].fields[0].type, FileTypeRef)

    def test_directory_type_ref(self) -> None:
        af = ArchFile(interfaces=[InterfaceDef(name="I", fields=[FieldDef(name="d", type=DirectoryTypeRef())])])
        result = _roundtrip(af)
        assert isinstance(result.interfaces[0].fields[0].type, DirectoryTypeRef)

    def test_named_type_ref(self) -> None:
        af = ArchFile(
            types=[
                TypeDef(
                    name="T",
                    fields=[FieldDef(name="item", type=NamedTypeRef(name="MyType"))],
                )
            ]
        )
        result = _roundtrip(af)
        field_type = result.types[0].fields[0].type
        assert isinstance(field_type, NamedTypeRef)
        assert field_type.name == "MyType"

    def test_nested_list_in_map(self) -> None:
        af = ArchFile(
            types=[
                TypeDef(
                    name="T",
                    fields=[
                        FieldDef(
                            name="nested",
                            type=MapTypeRef(
                                key_type=PrimitiveTypeRef(primitive=PrimitiveType.STRING),
                                value_type=ListTypeRef(element_type=PrimitiveTypeRef(primitive=PrimitiveType.INT)),
                            ),
                        )
                    ],
                )
            ]
        )
        result = _roundtrip(af)
        field_type = result.types[0].fields[0].type
        assert isinstance(field_type, MapTypeRef)
        assert isinstance(field_type.value_type, ListTypeRef)


class TestEnumDef:
    def test_enum_roundtrip(self) -> None:
        af = ArchFile(
            enums=[
                EnumDef(
                    name="Status",
                    values=["Active", "Inactive"],
                    title="Status Enum",
                    description="Describes activation state.",
                    tags=["core"],
                )
            ]
        )
        result = _roundtrip(af)
        assert result.enums[0].name == "Status"
        assert result.enums[0].values == ["Active", "Inactive"]
        assert result.enums[0].title == "Status Enum"
        assert result.enums[0].tags == ["core"]


class TestComponents:
    def test_component_roundtrip(self) -> None:
        af = ArchFile(
            components=[
                Component(
                    name="MyComp",
                    title="My Component",
                    description="Does things.",
                    tags=["important"],
                    requires=[InterfaceRef(name="Input")],
                    provides=[InterfaceRef(name="Output")],
                    is_external=False,
                )
            ]
        )
        result = _roundtrip(af)
        comp = result.components[0]
        assert comp.name == "MyComp"
        assert comp.title == "My Component"
        assert comp.requires[0].name == "Input"
        assert comp.provides[0].name == "Output"
        assert not comp.is_external

    def test_external_component(self) -> None:
        af = ArchFile(components=[Component(name="Ext", is_external=True)])
        result = _roundtrip(af)
        assert result.components[0].is_external

    def test_nested_component(self) -> None:
        af = ArchFile(
            components=[
                Component(
                    name="Parent",
                    components=[Component(name="Child")],
                )
            ]
        )
        result = _roundtrip(af)
        assert result.components[0].components[0].name == "Child"

    def test_connection_roundtrip(self) -> None:
        af = ArchFile(
            components=[
                Component(
                    name="Parent",
                    components=[Component(name="A"), Component(name="B")],
                    connections=[
                        Connection(
                            source=ConnectionEndpoint(entity="A"),
                            target=ConnectionEndpoint(entity="B"),
                            interface=InterfaceRef(name="Signal"),
                            protocol="gRPC",
                            is_async=True,
                            description="Data flow.",
                        )
                    ],
                )
            ]
        )
        result = _roundtrip(af)
        conn = result.components[0].connections[0]
        assert conn.source.entity == "A"
        assert conn.target.entity == "B"
        assert conn.interface.name == "Signal"
        assert conn.protocol == "gRPC"
        assert conn.is_async
        assert conn.description == "Data flow."


class TestSystems:
    def test_system_roundtrip(self) -> None:
        af = ArchFile(
            systems=[
                System(
                    name="MySys",
                    title="My System",
                    is_external=True,
                )
            ]
        )
        result = _roundtrip(af)
        sys = result.systems[0]
        assert sys.name == "MySys"
        assert sys.title == "My System"
        assert sys.is_external

    def test_nested_system(self) -> None:
        af = ArchFile(systems=[System(name="Outer", systems=[System(name="Inner")])])
        result = _roundtrip(af)
        assert result.systems[0].systems[0].name == "Inner"


class TestImports:
    def test_import_declaration_roundtrip(self) -> None:
        af = ArchFile(
            imports=[
                ImportDeclaration(
                    source_path="shared/types",
                    entities=["TypeA", "TypeB"],
                )
            ]
        )
        result = _roundtrip(af)
        imp = result.imports[0]
        assert imp.source_path == "shared/types"
        assert imp.entities == ["TypeA", "TypeB"]


class TestVersionedInterface:
    def test_versioned_interface_roundtrip(self) -> None:
        af = ArchFile(
            interfaces=[
                InterfaceDef(name="MyIface", version="v2"),
                InterfaceDef(name="MyIface", version=None),
            ]
        )
        result = _roundtrip(af)
        assert result.interfaces[0].version == "v2"
        assert result.interfaces[1].version is None


# ###############
# File I/O
# ###############


class TestFileIO:
    def test_write_and_read_artifact(self, tmp_path: Path) -> None:
        af = ArchFile(enums=[EnumDef(name="Color", values=["Red", "Green", "Blue"])])
        result = _roundtrip_file(af, tmp_path)
        assert result.enums[0].name == "Color"
        assert result.enums[0].values == ["Red", "Green", "Blue"]

    def test_artifact_file_is_valid_json(self, tmp_path: Path) -> None:
        import json

        af = ArchFile(components=[Component(name="C")])
        path = tmp_path / "test.archml.json"
        write_artifact(af, path)
        # Must be parseable as JSON
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "components" in data

    def test_roundtrip_parsed_file(self, tmp_path: Path) -> None:
        """Parsing a real .archml file and roundtripping through artifact."""
        source = """
enum Status { Active Inactive }

type Config {
    field timeout: Int
}

interface Request {
    field id: String
    field config: Config
}

component Worker {
    requires Request
}
"""
        af = parse(source)
        result = _roundtrip_file(af, tmp_path)
        assert result.enums[0].name == "Status"
        assert result.types[0].name == "Config"
        assert result.interfaces[0].name == "Request"
        assert result.components[0].name == "Worker"
