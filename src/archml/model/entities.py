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
    """A reference to an interface by name, optionally pinned to a version and bound to a channel."""

    name: str
    version: str | None = None
    via: str | None = None


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


class ChannelDef(BaseModel):
    """A named conduit that carries a specific interface within a system or component scope.

    Channels decouple providers from requirers: components bind to a channel
    by name rather than referencing each other directly.
    """

    name: str
    interface: InterfaceRef
    protocol: str | None = None
    is_async: bool = False
    description: str | None = None


class UserDef(BaseModel):
    """A human actor (role or persona) that interacts with the system.

    Users are leaf nodes: they declare required and provided interfaces but
    cannot contain sub-entities or channels.
    """

    name: str
    title: str | None = None
    description: str | None = None
    tags: list[str] = _Field(default_factory=list)
    requires: list[InterfaceRef] = _Field(default_factory=list)
    provides: list[InterfaceRef] = _Field(default_factory=list)
    is_external: bool = False
    qualified_name: str = ""


class Component(BaseModel):
    """A module with declared interface bindings and optional nested sub-components."""

    name: str
    title: str | None = None
    description: str | None = None
    tags: list[str] = _Field(default_factory=list)
    requires: list[InterfaceRef] = _Field(default_factory=list)
    provides: list[InterfaceRef] = _Field(default_factory=list)
    channels: list[ChannelDef] = _Field(default_factory=list)
    components: list[Component] = _Field(default_factory=list)
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
    channels: list[ChannelDef] = _Field(default_factory=list)
    components: list[Component] = _Field(default_factory=list)
    systems: list[System] = _Field(default_factory=list)
    users: list[UserDef] = _Field(default_factory=list)
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
    users: list[UserDef] = _Field(default_factory=list)


# Resolve forward references in self-referential models.
Component.model_rebuild()
System.model_rebuild()
ArchFile.model_rebuild()
