# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Type system representations for the ArchML semantic model."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel
from pydantic import Field as _Field

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


class PrimitiveTypeRef(BaseModel):
    """Reference to a primitive type."""

    kind: Literal["primitive"] = "primitive"
    primitive: PrimitiveType


class FileTypeRef(BaseModel):
    """Reference to the File filesystem type."""

    kind: Literal["file"] = "file"


class DirectoryTypeRef(BaseModel):
    """Reference to the Directory filesystem type."""

    kind: Literal["directory"] = "directory"


class ListTypeRef(BaseModel):
    """Reference to a parameterized List<T> type."""

    kind: Literal["list"] = "list"
    element_type: TypeRef


class MapTypeRef(BaseModel):
    """Reference to a parameterized Map<K, V> type."""

    kind: Literal["map"] = "map"
    key_type: TypeRef
    value_type: TypeRef


class OptionalTypeRef(BaseModel):
    """Reference to a parameterized Optional<T> type."""

    kind: Literal["optional"] = "optional"
    inner_type: TypeRef


class NamedTypeRef(BaseModel):
    """Reference to a named custom type, enum, or interface."""

    kind: Literal["named"] = "named"
    name: str


# A field type reference — one of the built-in, container, or named types.
# The `kind` discriminator field enables fast, unambiguous deserialization.
TypeRef = Annotated[
    PrimitiveTypeRef | FileTypeRef | DirectoryTypeRef | ListTypeRef | MapTypeRef | OptionalTypeRef | NamedTypeRef,
    _Field(discriminator="kind"),
]


class Field(BaseModel):
    """A named, typed data element in a type or interface definition."""

    name: str
    type: TypeRef
    description: str | None = None
    schema: str | None = None
    filetype: str | None = None


# Resolve forward references for models that use TypeRef.
ListTypeRef.model_rebuild()
MapTypeRef.model_rebuild()
OptionalTypeRef.model_rebuild()
Field.model_rebuild()
