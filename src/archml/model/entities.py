# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Core architectural entities for the ArchML semantic model."""

from __future__ import annotations

from dataclasses import dataclass, field

from archml.model.types import Field

# ###############
# Public Interface
# ###############


@dataclass
class InterfaceRef:
    """A reference to an interface by name, optionally pinned to a version."""

    name: str
    version: str | None = None


@dataclass
class EnumDef:
    """An enumeration definition."""

    name: str
    values: list[str] = field(default_factory=list)
    title: str | None = None
    description: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class TypeDef:
    """A reusable composite data type definition."""

    name: str
    fields: list[Field] = field(default_factory=list)
    title: str | None = None
    description: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class InterfaceDef:
    """An interface definition — a named, versioned contract of typed fields."""

    name: str
    version: str | None = None
    fields: list[Field] = field(default_factory=list)
    title: str | None = None
    description: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class ConnectionEndpoint:
    """One end of a connection: a named entity."""

    entity: str


@dataclass
class Connection:
    """A directed data-flow edge linking a required interface to a provided one."""

    source: ConnectionEndpoint
    target: ConnectionEndpoint
    interface: InterfaceRef
    protocol: str | None = None
    is_async: bool = False
    description: str | None = None


@dataclass
class Component:
    """A module with declared interface ports and optional nested sub-components."""

    name: str
    title: str | None = None
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    requires: list[InterfaceRef] = field(default_factory=list)
    provides: list[InterfaceRef] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    is_external: bool = False


@dataclass
class System:
    """A group of components (or sub-systems) working toward a shared goal."""

    name: str
    title: str | None = None
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    systems: list[System] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    is_external: bool = False


@dataclass
class ImportDeclaration:
    """An import statement that brings named entities from another file into scope."""

    source_path: str
    entities: list[str] = field(default_factory=list)


@dataclass
class ArchFile:
    """Top-level model representing the parsed contents of a single .archml file."""

    imports: list[ImportDeclaration] = field(default_factory=list)
    enums: list[EnumDef] = field(default_factory=list)
    types: list[TypeDef] = field(default_factory=list)
    interfaces: list[InterfaceDef] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    systems: list[System] = field(default_factory=list)
