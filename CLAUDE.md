# CLAUDE.md — ArchML Development Guide

## Project Overview

ArchML is a text-based DSL for defining software architecture alongside code.
It covers functional, behavioral, and deployment architecture domains with consistency checking, navigable web views, and native Sphinx integration. Architecture files use the `.archml` extension.


## Tech Stack

- **Language**: Python (3.12+)
- **Package manager**: uv
- **Linter/formatter**: ruff
- **Type checker**: ty
- **Testing**: pytest
- **Documentation**: Sphinx
- **Distribution**: PyPI


## Project Structure (Target)

## Common Commands

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest

# Run a specific test file or test
uv run pytest tests/parser/test_lexer.py
uv run pytest -k "test_parse_component"

# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Type check
uv run ty check src/
```

## Development Methodology

Every new feature requires thorough testing before it is considered complete. The workflow is:

1. Write or update the relevant specification/design if needed.
2. Implement the feature in `src/archml/`.
3. Write tests in `tests/` covering normal cases, edge cases, and error cases.
4. Ensure all tests pass, ruff reports no issues, and ty finds no type errors using `uv run tools/ci.py`.
5. Commit with a clear message describing the change.

Tests are not optional.
A feature without tests is not done.


## ArchML Language Quick Reference

Full language reference: `docs/LANGUAGE_REFERENCE.md`
Annotated example: `docs/LANGUAGE_EXAMPLE.md`



## Coding Conventions

- Use `ruff` defaults for formatting and linting rules.
- All public APIs must have type annotations.
- Prefer dataclasses or attrs for model types.
- Keep modules focused: one responsibility per module.
- The test directory structure mirrors the source structure. Every module in `src/archml/<package>/` has a corresponding directory in `tests/<package>/`. Test files are prefixed with `test_`: `src/archml/parser/lexer.py` -> `tests/parser/test_lexer.py`.
- Use proper docstrings for public functions.
- Every Python file follows this layout:

```python
# Copyright ...
# SPDX-License-Identifier: Apache-2.0

import ...

# ###############
# Public Interface
# ###############

def public_function() -> None:
    ...

# ################
# Implementation
# ################

def _private_helper() -> None:
    ...
```

The copyright header and imports come first. Public interface (classes, functions, constants) is separated from private implementation by section comments. All private members are prefixed with an underscore.