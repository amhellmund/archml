# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Semantic model for ArchML (systems, components, interfaces, etc.)."""

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

__all__ = [
    # Type system
    "PrimitiveType",
    "PrimitiveTypeRef",
    "FileTypeRef",
    "DirectoryTypeRef",
    "ListTypeRef",
    "MapTypeRef",
    "OptionalTypeRef",
    "NamedTypeRef",
    "TypeRef",
    "Field",
    # Entities
    "InterfaceRef",
    "EnumDef",
    "TypeDef",
    "InterfaceDef",
    "ConnectionEndpoint",
    "Connection",
    "Component",
    "System",
    "ImportDeclaration",
    "ArchFile",
]
