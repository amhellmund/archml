# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Compiler pipeline for .archml files: scanning, parsing, and semantic analysis."""

from archml.compiler.artifact import ARTIFACT_SUFFIX, deserialize, read_artifact, serialize, write_artifact
from archml.compiler.build import CompilerError, compile_files
from archml.compiler.parser import ParseError, parse
from archml.compiler.semantic_analysis import SemanticError, analyze

__all__ = [
    "parse",
    "ParseError",
    "analyze",
    "SemanticError",
    "serialize",
    "deserialize",
    "write_artifact",
    "read_artifact",
    "ARTIFACT_SUFFIX",
    "compile_files",
    "CompilerError",
]
