# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Compiler pipeline for .archml files: scanning, parsing, semantic analysis, and build."""

from archml.compiler.build import CompilerError, compile_files
from archml.compiler.parser import ParseError, parse
from archml.compiler.semantic_analysis import SemanticError, analyze

__all__ = [
    "compile_files",
    "CompilerError",
    "parse",
    "ParseError",
    "analyze",
    "SemanticError",
]
