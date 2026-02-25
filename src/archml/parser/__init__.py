# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Lexer and parser for .archml files."""

from archml.parser.parser import ParseError, parse

__all__ = [
    "parse",
    "ParseError",
]
