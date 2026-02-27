# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Serialization and deserialization of compiled ArchFile artifacts.

Artifacts are stored as compact JSON files for portability and human-readability.
The format is versioned so future schema changes can be detected.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
    TypeRef,
)

# ###############
# Public Interface
# ###############

ARTIFACT_FORMAT_VERSION = "1"


def serialize(arch_file: ArchFile) -> str:
    """Serialize an ArchFile to a compact JSON string."""
    return json.dumps(_arch_file_to_dict(arch_file), separators=(",", ":"))


def deserialize(data: str) -> ArchFile:
    """Deserialize an ArchFile from a JSON string.

    Args:
        data: JSON string produced by :func:`serialize`.

    Returns:
        The reconstructed :class:`ArchFile` model.

    Raises:
        ValueError: If the artifact format version is not recognised.
    """
    obj = json.loads(data)
    version = obj.get("v")
    if version != ARTIFACT_FORMAT_VERSION:
        raise ValueError(f"Unsupported artifact format version: {version!r}")
    return _arch_file_from_dict(obj)


def write_artifact(arch_file: ArchFile, path: Path) -> None:
    """Write a compiled artifact to *path*, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize(arch_file), encoding="utf-8")


def read_artifact(path: Path) -> ArchFile:
    """Read and deserialize a compiled artifact from *path*."""
    return deserialize(path.read_text(encoding="utf-8"))


# ################
# Implementation
# ################


def _arch_file_to_dict(arch_file: ArchFile) -> dict[str, Any]:
    return {
        "v": ARTIFACT_FORMAT_VERSION,
        "imports": [_import_to_dict(i) for i in arch_file.imports],
        "enums": [_enum_to_dict(e) for e in arch_file.enums],
        "types": [_type_to_dict(t) for t in arch_file.types],
        "interfaces": [_interface_to_dict(i) for i in arch_file.interfaces],
        "components": [_component_to_dict(c) for c in arch_file.components],
        "systems": [_system_to_dict(s) for s in arch_file.systems],
    }


def _arch_file_from_dict(obj: dict[str, Any]) -> ArchFile:
    return ArchFile(
        imports=[_import_from_dict(i) for i in obj.get("imports", [])],
        enums=[_enum_from_dict(e) for e in obj.get("enums", [])],
        types=[_type_from_dict(t) for t in obj.get("types", [])],
        interfaces=[_interface_from_dict(i) for i in obj.get("interfaces", [])],
        components=[_component_from_dict(c) for c in obj.get("components", [])],
        systems=[_system_from_dict(s) for s in obj.get("systems", [])],
    )


def _import_to_dict(imp: ImportDeclaration) -> dict[str, Any]:
    return {"path": imp.source_path, "entities": imp.entities}


def _import_from_dict(obj: dict[str, Any]) -> ImportDeclaration:
    return ImportDeclaration(source_path=obj["path"], entities=obj["entities"])


def _enum_to_dict(enum: EnumDef) -> dict[str, Any]:
    d: dict[str, Any] = {"name": enum.name, "values": enum.values, "tags": enum.tags}
    if enum.title is not None:
        d["title"] = enum.title
    if enum.description is not None:
        d["description"] = enum.description
    return d


def _enum_from_dict(obj: dict[str, Any]) -> EnumDef:
    return EnumDef(
        name=obj["name"],
        values=obj["values"],
        title=obj.get("title"),
        description=obj.get("description"),
        tags=obj.get("tags", []),
    )


def _field_to_dict(f: Field) -> dict[str, Any]:
    d: dict[str, Any] = {"name": f.name, "type": _type_ref_to_dict(f.type)}
    if f.description is not None:
        d["description"] = f.description
    if f.schema is not None:
        d["schema"] = f.schema
    if f.filetype is not None:
        d["filetype"] = f.filetype
    return d


def _field_from_dict(obj: dict[str, Any]) -> Field:
    return Field(
        name=obj["name"],
        type=_type_ref_from_dict(obj["type"]),
        description=obj.get("description"),
        schema=obj.get("schema"),
        filetype=obj.get("filetype"),
    )


def _type_to_dict(type_def: TypeDef) -> dict[str, Any]:
    d: dict[str, Any] = {
        "name": type_def.name,
        "fields": [_field_to_dict(f) for f in type_def.fields],
        "tags": type_def.tags,
    }
    if type_def.title is not None:
        d["title"] = type_def.title
    if type_def.description is not None:
        d["description"] = type_def.description
    return d


def _type_from_dict(obj: dict[str, Any]) -> TypeDef:
    return TypeDef(
        name=obj["name"],
        fields=[_field_from_dict(f) for f in obj.get("fields", [])],
        title=obj.get("title"),
        description=obj.get("description"),
        tags=obj.get("tags", []),
    )


def _interface_to_dict(iface: InterfaceDef) -> dict[str, Any]:
    d: dict[str, Any] = {
        "name": iface.name,
        "fields": [_field_to_dict(f) for f in iface.fields],
        "tags": iface.tags,
    }
    if iface.version is not None:
        d["version"] = iface.version
    if iface.title is not None:
        d["title"] = iface.title
    if iface.description is not None:
        d["description"] = iface.description
    return d


def _interface_from_dict(obj: dict[str, Any]) -> InterfaceDef:
    return InterfaceDef(
        name=obj["name"],
        version=obj.get("version"),
        fields=[_field_from_dict(f) for f in obj.get("fields", [])],
        title=obj.get("title"),
        description=obj.get("description"),
        tags=obj.get("tags", []),
    )


def _interface_ref_to_dict(ref: InterfaceRef) -> dict[str, Any]:
    d: dict[str, Any] = {"name": ref.name}
    if ref.version is not None:
        d["version"] = ref.version
    return d


def _interface_ref_from_dict(obj: dict[str, Any]) -> InterfaceRef:
    return InterfaceRef(name=obj["name"], version=obj.get("version"))


def _connection_endpoint_to_dict(ep: ConnectionEndpoint) -> dict[str, str]:
    return {"entity": ep.entity}


def _connection_endpoint_from_dict(obj: dict[str, Any]) -> ConnectionEndpoint:
    return ConnectionEndpoint(entity=obj["entity"])


def _connection_to_dict(conn: Connection) -> dict[str, Any]:
    d: dict[str, Any] = {
        "source": _connection_endpoint_to_dict(conn.source),
        "target": _connection_endpoint_to_dict(conn.target),
        "interface": _interface_ref_to_dict(conn.interface),
        "async": conn.is_async,
    }
    if conn.protocol is not None:
        d["protocol"] = conn.protocol
    if conn.description is not None:
        d["description"] = conn.description
    return d


def _connection_from_dict(obj: dict[str, Any]) -> Connection:
    return Connection(
        source=_connection_endpoint_from_dict(obj["source"]),
        target=_connection_endpoint_from_dict(obj["target"]),
        interface=_interface_ref_from_dict(obj["interface"]),
        protocol=obj.get("protocol"),
        is_async=obj.get("async", False),
        description=obj.get("description"),
    )


def _component_to_dict(comp: Component) -> dict[str, Any]:
    d: dict[str, Any] = {
        "name": comp.name,
        "tags": comp.tags,
        "requires": [_interface_ref_to_dict(r) for r in comp.requires],
        "provides": [_interface_ref_to_dict(p) for p in comp.provides],
        "components": [_component_to_dict(c) for c in comp.components],
        "connections": [_connection_to_dict(c) for c in comp.connections],
        "external": comp.is_external,
    }
    if comp.title is not None:
        d["title"] = comp.title
    if comp.description is not None:
        d["description"] = comp.description
    return d


def _component_from_dict(obj: dict[str, Any]) -> Component:
    return Component(
        name=obj["name"],
        title=obj.get("title"),
        description=obj.get("description"),
        tags=obj.get("tags", []),
        requires=[_interface_ref_from_dict(r) for r in obj.get("requires", [])],
        provides=[_interface_ref_from_dict(p) for p in obj.get("provides", [])],
        components=[_component_from_dict(c) for c in obj.get("components", [])],
        connections=[_connection_from_dict(c) for c in obj.get("connections", [])],
        is_external=obj.get("external", False),
    )


def _system_to_dict(system: System) -> dict[str, Any]:
    d: dict[str, Any] = {
        "name": system.name,
        "tags": system.tags,
        "requires": [_interface_ref_to_dict(r) for r in system.requires],
        "provides": [_interface_ref_to_dict(p) for p in system.provides],
        "components": [_component_to_dict(c) for c in system.components],
        "systems": [_system_to_dict(s) for s in system.systems],
        "connections": [_connection_to_dict(c) for c in system.connections],
        "external": system.is_external,
    }
    if system.title is not None:
        d["title"] = system.title
    if system.description is not None:
        d["description"] = system.description
    return d


def _system_from_dict(obj: dict[str, Any]) -> System:
    return System(
        name=obj["name"],
        title=obj.get("title"),
        description=obj.get("description"),
        tags=obj.get("tags", []),
        requires=[_interface_ref_from_dict(r) for r in obj.get("requires", [])],
        provides=[_interface_ref_from_dict(p) for p in obj.get("provides", [])],
        components=[_component_from_dict(c) for c in obj.get("components", [])],
        systems=[_system_from_dict(s) for s in obj.get("systems", [])],
        connections=[_connection_from_dict(c) for c in obj.get("connections", [])],
        is_external=obj.get("external", False),
    )


def _type_ref_to_dict(type_ref: TypeRef) -> dict[str, Any]:
    """Encode a TypeRef as a tagged dict with compact keys."""
    if isinstance(type_ref, PrimitiveTypeRef):
        return {"k": "primitive", "t": type_ref.primitive.value}
    if isinstance(type_ref, FileTypeRef):
        return {"k": "file"}
    if isinstance(type_ref, DirectoryTypeRef):
        return {"k": "directory"}
    if isinstance(type_ref, ListTypeRef):
        return {"k": "list", "e": _type_ref_to_dict(type_ref.element_type)}
    if isinstance(type_ref, MapTypeRef):
        return {
            "k": "map",
            "key": _type_ref_to_dict(type_ref.key_type),
            "val": _type_ref_to_dict(type_ref.value_type),
        }
    if isinstance(type_ref, OptionalTypeRef):
        return {"k": "optional", "i": _type_ref_to_dict(type_ref.inner_type)}
    # NamedTypeRef is the only remaining variant.
    assert isinstance(type_ref, NamedTypeRef)
    return {"k": "named", "n": type_ref.name}


def _type_ref_from_dict(obj: dict[str, Any]) -> TypeRef:
    """Decode a TypeRef from a tagged dict."""
    kind = obj["k"]
    if kind == "primitive":
        return PrimitiveTypeRef(PrimitiveType(obj["t"]))
    if kind == "file":
        return FileTypeRef()
    if kind == "directory":
        return DirectoryTypeRef()
    if kind == "list":
        return ListTypeRef(_type_ref_from_dict(obj["e"]))
    if kind == "map":
        return MapTypeRef(_type_ref_from_dict(obj["key"]), _type_ref_from_dict(obj["val"]))
    if kind == "optional":
        return OptionalTypeRef(_type_ref_from_dict(obj["i"]))
    if kind == "named":
        return NamedTypeRef(obj["n"])
    raise ValueError(f"Unknown type ref kind: {kind!r}")
