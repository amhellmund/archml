# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Compiler pipeline for .archml files: scanning, parsing, and semantic analysis."""

from archml.compiler.parser import ParseError, parse
from archml.compiler.semantic_analysis import SemanticError, analyze

__all__ = [
    "parse",
    "ParseError",
    "analyze",
    "SemanticError",
]
