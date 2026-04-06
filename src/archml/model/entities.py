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
    """A reference to an interface by name.

    The optional ``port_name`` holds the explicit port alias assigned with the
    ``as`` keyword (e.g. ``requires PaymentRequest as pay_in``).  When absent
    the effective port name defaults to the interface name.

    ``variants`` lists the variant names for which this port is active.  An
    empty list means the port is baseline (present in all variants).
    """

    name: str
    port_name: str | None = None
    variants: list[str] = _Field(default_factory=list)
    line: int = 0


class NamedDef(BaseModel):
    """Base class for named definition entities.

    Shared by ``EnumDef``, ``TypeDef``, and ``InterfaceDef``.
    """

    name: str
    description: str | None = None
    attributes: dict[str, list[str]] = _Field(default_factory=dict)
    line: int = 0


class EnumDef(NamedDef):
    """An enumeration definition."""

    values: list[str] = _Field(default_factory=list)


class TypeDef(NamedDef):
    """A reusable composite data type definition."""

    fields: list[FieldDef] = _Field(default_factory=list)


class InterfaceDef(NamedDef):
    """An interface definition — a named contract of typed fields."""

    variants: list[str] = _Field(default_factory=list)
    fields: list[FieldDef] = _Field(default_factory=list)
    qualified_name: str = ""


class ConnectDef(BaseModel):
    """A ``connect`` statement wiring ports via a named channel.

    Each of the three syntactic forms is encoded as follows:

    - Full chain ``connect A.p -> $ch -> B.q``:
      ``src_entity="A"``, ``src_port="p"``, ``channel="ch"``,
      ``dst_entity="B"``, ``dst_port="q"``
    - One-sided src ``connect A.p -> $ch``:
      ``src_entity="A"``, ``src_port="p"``, ``channel="ch"``,
      ``dst_entity=None``, ``dst_port=None``
    - One-sided dst ``connect $ch -> B.q``:
      ``src_entity=None``, ``src_port=None``, ``channel="ch"``,
      ``dst_entity="B"``, ``dst_port="q"``

    For a port on the current scope's own boundary (no entity qualifier),
    ``src_entity`` / ``dst_entity`` is ``None``.

    ``variants`` lists the variant names for which this connection is active.
    An empty list means the connection is baseline (present in all variants).
    """

    src_entity: str | None = None
    src_port: str | None = None
    channel: str | None = None
    dst_entity: str | None = None
    dst_port: str | None = None
    variants: list[str] = _Field(default_factory=list)
    line: int = 0


class ExposeDef(BaseModel):
    """An ``expose`` statement promoting a sub-entity's port to the enclosing boundary.

    ``expose Entity.port_name [as new_name]``

    ``variants`` lists the variant names for which this exposure is active.
    An empty list means the exposure is baseline (present in all variants).
    """

    entity: str
    port: str
    as_name: str | None = None
    variants: list[str] = _Field(default_factory=list)
    line: int = 0


class ArchEntity(BaseModel):
    """Base class for architectural actor entities.

    Shared by ``UserDef``, ``Component``, and ``System``.
    """

    name: str
    description: str | None = None
    variants: list[str] = _Field(default_factory=list)
    requires: list[InterfaceRef] = _Field(default_factory=list)
    provides: list[InterfaceRef] = _Field(default_factory=list)
    attributes: dict[str, list[str]] = _Field(default_factory=dict)
    is_external: bool = False
    qualified_name: str = ""
    line: int = 0


class UserDef(ArchEntity):
    """A human actor (role or persona) that interacts with the system.

    Users are leaf nodes: they declare required and provided interfaces but
    cannot contain sub-entities or channels.
    """


class ContainerEntity(ArchEntity):
    """Base class for entities that can contain sub-components and channels.

    Shared by ``Component`` and ``System``.
    """

    interfaces: list[InterfaceDef] = _Field(default_factory=list)
    connects: list[ConnectDef] = _Field(default_factory=list)
    exposes: list[ExposeDef] = _Field(default_factory=list)
    is_stub: bool = False


class Component(ContainerEntity):
    """A module with declared interface bindings and optional nested sub-components."""

    components: list[Component] = _Field(default_factory=list)


class System(ContainerEntity):
    """A group of components (or sub-systems) working toward a shared goal."""

    components: list[Component] = _Field(default_factory=list)
    systems: list[System] = _Field(default_factory=list)
    users: list[UserDef] = _Field(default_factory=list)


class ImportDeclaration(BaseModel):
    """An import statement that brings named entities from another file into scope.

    ``entities`` lists the original names as they appear in the source file.
    ``aliases`` maps each original name to its local alias when an ``as`` clause
    is present (e.g. ``from path import Foo as Bar`` → ``aliases={"Foo": "Bar"}``).
    The local name for entity ``E`` is ``aliases.get(E, E)``.
    """

    source_path: str
    entities: list[str] = _Field(default_factory=list)
    aliases: dict[str, str] = _Field(default_factory=dict)
    line: int = 0


class ArchFile(BaseModel):
    """Top-level model representing the parsed contents of a single .archml file."""

    imports: list[ImportDeclaration] = _Field(default_factory=list)
    enums: list[EnumDef] = _Field(default_factory=list)
    types: list[TypeDef] = _Field(default_factory=list)
    interfaces: list[InterfaceDef] = _Field(default_factory=list)
    components: list[Component] = _Field(default_factory=list)
    systems: list[System] = _Field(default_factory=list)
    users: list[UserDef] = _Field(default_factory=list)
    connects: list[ConnectDef] = _Field(default_factory=list)


# Resolve forward references in self-referential models.
Component.model_rebuild()
System.model_rebuild()
ArchFile.model_rebuild()
