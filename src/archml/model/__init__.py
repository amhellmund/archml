# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Semantic model for ArchML (systems, components, interfaces, etc.)."""

from archml.model.entities import (
    ArchFile,
    Component,
    ConnectDef,
    EnumDef,
    ExposeDef,
    ImportDeclaration,
    InterfaceDef,
    InterfaceRef,
    System,
    TypeDef,
    UserDef,
)
from archml.model.types import (
    FieldDef,
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
    "ConnectDef",
    "ExposeDef",
    "Component",
    "System",
    "UserDef",
    "ImportDeclaration",
    "ArchFile",
]
