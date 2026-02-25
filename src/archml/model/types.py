# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Type system representations for the ArchML semantic model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ###############
# Public Interface
# ###############


class PrimitiveType(Enum):
    """Primitive types supported by the ArchML type system."""

    STRING = "String"
    INT = "Int"
    FLOAT = "Float"
    DECIMAL = "Decimal"
    BOOL = "Bool"
    BYTES = "Bytes"
    TIMESTAMP = "Timestamp"
    DATETIME = "Datetime"


@dataclass
class PrimitiveTypeRef:
    """Reference to a primitive type."""

    primitive: PrimitiveType


@dataclass
class FileTypeRef:
    """Reference to the File filesystem type."""


@dataclass
class DirectoryTypeRef:
    """Reference to the Directory filesystem type."""


@dataclass
class ListTypeRef:
    """Reference to a parameterized List<T> type."""

    element_type: TypeRef


@dataclass
class MapTypeRef:
    """Reference to a parameterized Map<K, V> type."""

    key_type: TypeRef
    value_type: TypeRef


@dataclass
class OptionalTypeRef:
    """Reference to a parameterized Optional<T> type."""

    inner_type: TypeRef


@dataclass
class NamedTypeRef:
    """Reference to a named custom type, enum, or interface."""

    name: str


# A field type reference — one of the built-in, container, or named types.
TypeRef = (
    PrimitiveTypeRef
    | FileTypeRef
    | DirectoryTypeRef
    | ListTypeRef
    | MapTypeRef
    | OptionalTypeRef
    | NamedTypeRef
)


@dataclass
class Field:
    """A named, typed data element in a type or interface definition."""

    name: str
    type: TypeRef
    description: str | None = None
    schema: str | None = None
    filetype: str | None = None
