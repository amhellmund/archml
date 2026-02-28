# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Core architectural entities for the ArchML semantic model."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic import Field as _Field

from archml.model.types import FieldDef

# ###############
# Public Interface
# ###############


class InterfaceRef(BaseModel):
    """A reference to an interface by name, optionally pinned to a version."""

    name: str
    version: str | None = None


class EnumDef(BaseModel):
    """An enumeration definition."""

    name: str
    values: list[str] = _Field(default_factory=list)
    title: str | None = None
    description: str | None = None
    tags: list[str] = _Field(default_factory=list)


class TypeDef(BaseModel):
    """A reusable composite data type definition."""

    name: str
    fields: list[FieldDef] = _Field(default_factory=list)
    title: str | None = None
    description: str | None = None
    tags: list[str] = _Field(default_factory=list)


class InterfaceDef(BaseModel):
    """An interface definition — a named, versioned contract of typed fields."""

    name: str
    version: str | None = None
    fields: list[FieldDef] = _Field(default_factory=list)
    title: str | None = None
    description: str | None = None
    tags: list[str] = _Field(default_factory=list)
    qualified_name: str = ""


class ConnectionEndpoint(BaseModel):
    """One end of a connection: a named entity."""

    entity: str


class Connection(BaseModel):
    """A directed data-flow edge linking a required interface to a provided one."""

    source: ConnectionEndpoint
    target: ConnectionEndpoint
    interface: InterfaceRef
    protocol: str | None = None
    is_async: bool = False
    description: str | None = None


class Component(BaseModel):
    """A module with declared interface ports and optional nested sub-components."""

    name: str
    title: str | None = None
    description: str | None = None
    tags: list[str] = _Field(default_factory=list)
    requires: list[InterfaceRef] = _Field(default_factory=list)
    provides: list[InterfaceRef] = _Field(default_factory=list)
    components: list[Component] = _Field(default_factory=list)
    connections: list[Connection] = _Field(default_factory=list)
    is_external: bool = False
    qualified_name: str = ""


class System(BaseModel):
    """A group of components (or sub-systems) working toward a shared goal."""

    name: str
    title: str | None = None
    description: str | None = None
    tags: list[str] = _Field(default_factory=list)
    requires: list[InterfaceRef] = _Field(default_factory=list)
    provides: list[InterfaceRef] = _Field(default_factory=list)
    components: list[Component] = _Field(default_factory=list)
    systems: list[System] = _Field(default_factory=list)
    connections: list[Connection] = _Field(default_factory=list)
    is_external: bool = False
    qualified_name: str = ""


class ImportDeclaration(BaseModel):
    """An import statement that brings named entities from another file into scope."""

    source_path: str
    entities: list[str] = _Field(default_factory=list)


class ArchFile(BaseModel):
    """Top-level model representing the parsed contents of a single .archml file."""

    imports: list[ImportDeclaration] = _Field(default_factory=list)
    enums: list[EnumDef] = _Field(default_factory=list)
    types: list[TypeDef] = _Field(default_factory=list)
    interfaces: list[InterfaceDef] = _Field(default_factory=list)
    components: list[Component] = _Field(default_factory=list)
    systems: list[System] = _Field(default_factory=list)


# Resolve forward references in self-referential models.
Component.model_rebuild()
System.model_rebuild()
