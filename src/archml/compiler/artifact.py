# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Serialization of compiled ArchFile models to/from JSON artifacts.

Pydantic's built-in serialization is used, so no manual dict-to-JSON mapping
is required.  The JSON format is compact (no indentation) and includes full
type discriminators for TypeRef variants, enabling reliable deserialization.
"""

from pathlib import Path

from archml.model.entities import ArchFile

# ###############
# Public Interface
# ###############

ARTIFACT_SUFFIX = ".archml.json"


def serialize(arch_file: ArchFile) -> str:
    """Serialize an ArchFile to a compact JSON string.

    Args:
        arch_file: The compiled ArchFile model to serialize.

    Returns:
        A compact JSON string representation of the model.
    """
    return arch_file.model_dump_json()


def deserialize(data: str) -> ArchFile:
    """Deserialize an ArchFile from a JSON string.

    Args:
        data: A JSON string produced by :func:`serialize`.

    Returns:
        The reconstructed ArchFile model.

    Raises:
        pydantic.ValidationError: If the JSON data does not conform to the
            ArchFile schema.
    """
    return ArchFile.model_validate_json(data)


def write_artifact(arch_file: ArchFile, path: Path) -> None:
    """Write a compiled ArchFile artifact to a file.

    The parent directory must already exist.

    Args:
        arch_file: The compiled ArchFile model to write.
        path: Destination file path.
    """
    path.write_text(arch_file.model_dump_json(), encoding="utf-8")


def read_artifact(path: Path) -> ArchFile:
    """Read a compiled ArchFile artifact from a file.

    Args:
        path: Path to an artifact file written by :func:`write_artifact`.

    Returns:
        The reconstructed ArchFile model.

    Raises:
        pydantic.ValidationError: If the file contents do not conform to the
            ArchFile schema.
        FileNotFoundError: If *path* does not exist.
    """
    return ArchFile.model_validate_json(path.read_text(encoding="utf-8"))
