# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Semantic model for ArchML (systems, components, interfaces, etc.)."""

from archml.model.entities import (
    ArchFile,
    ChannelDef,
    Component,
    EnumDef,
    ImportDeclaration,
    InterfaceDef,
    InterfaceRef,
    System,
    TypeDef,
    UserDef,
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
    "FieldDef",
    # Entities
    "InterfaceRef",
    "EnumDef",
    "TypeDef",
    "InterfaceDef",
    "ChannelDef",
    "Component",
    "System",
    "UserDef",
    "ImportDeclaration",
    "ArchFile",
]
