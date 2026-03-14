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
    """A reference to an interface by name, optionally pinned to a version.

    The optional ``port_name`` holds the explicit port alias assigned with the
    ``as`` keyword (e.g. ``requires PaymentRequest as pay_in``).  When absent
    the effective port name defaults to the interface name.
    """

    name: str
    version: str | None = None
    port_name: str | None = None


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


class ConnectDef(BaseModel):
    """A ``connect`` statement wiring ports, optionally via a named channel.

    Each of the four syntactic forms is encoded as follows:

    - Full chain ``connect A.p -> $ch -> B.q``:
      ``src_entity="A"``, ``src_port="p"``, ``channel="ch"``,
      ``dst_entity="B"``, ``dst_port="q"``
    - One-sided src ``connect A.p -> $ch``:
      ``src_entity="A"``, ``src_port="p"``, ``channel="ch"``,
      ``dst_entity=None``, ``dst_port=None``
    - One-sided dst ``connect $ch -> B.q``:
      ``src_entity=None``, ``src_port=None``, ``channel="ch"``,
      ``dst_entity="B"``, ``dst_port="q"``
    - Direct ``connect A.p -> B.q``:
      ``src_entity="A"``, ``src_port="p"``, ``channel=None``,
      ``dst_entity="B"``, ``dst_port="q"``

    For a port on the current scope's own boundary (no entity qualifier),
    ``src_entity`` / ``dst_entity`` is ``None``.
    """

    src_entity: str | None = None
    src_port: str | None = None
    channel: str | None = None
    dst_entity: str | None = None
    dst_port: str | None = None
    protocol: str | None = None
    is_async: bool = False
    description: str | None = None


class ExposeDef(BaseModel):
    """An ``expose`` statement promoting a sub-entity's port to the enclosing boundary.

    ``expose Entity.port_name [as new_name]``
    """

    entity: str
    port: str
    as_name: str | None = None


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
    components: list[Component] = _Field(default_factory=list)
    connects: list[ConnectDef] = _Field(default_factory=list)
    exposes: list[ExposeDef] = _Field(default_factory=list)
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
    users: list[UserDef] = _Field(default_factory=list)
    connects: list[ConnectDef] = _Field(default_factory=list)
    exposes: list[ExposeDef] = _Field(default_factory=list)
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
