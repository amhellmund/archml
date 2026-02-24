# CLAUDE.md — ArchML Development Guide

## Project Overview

ArchML is a text-based DSL for defining software architecture alongside code. It covers functional, behavioral, and deployment architecture domains with consistency checking, navigable web views, and native Sphinx integration. Architecture files use the `.archml` extension.

The project is in early development. The DSL syntax for functional architecture is specified in `docs/LANGUAGE_SYNTAX.md`. The overall vision and landscape analysis are in `docs/PROJECT_SCOPE.md`.

## Tech Stack

- **Language**: Python (3.12+)
- **Package manager**: uv
- **Linter/formatter**: ruff
- **Type checker**: ty
- **Testing**: pytest
- **Documentation**: Sphinx (ArchML views will embed natively via a Sphinx extension)
- **Distribution**: PyPI

## Project Structure (Target)

```
archml/
├── CLAUDE.md
├── README.md
├── LICENSE
├── pyproject.toml
├── docs/
│   ├── PROJECT_SCOPE.md
│   ├── LANGUAGE_SYNTAX.md
│   └── sphinx/              # Sphinx documentation source
├── src/
│   └── archml/
│       ├── __init__.py
│       ├── parser/          # Lexer and parser for .archml files
│       ├── model/           # Semantic model (systems, components, interfaces, etc.)
│       ├── validation/      # Consistency checks (dangling refs, unused interfaces)
│       ├── views/           # View generation and rendering
│       ├── sphinx_ext/      # Sphinx extension for embedding architecture views
│       ├── lsp/             # Language server (LSP) for VS Code integration
│       └── cli/             # Command-line interface
└── tests/                   # All tests (mirrors src/ structure)
    ├── parser/
    ├── model/
    ├── validation/
    ├── views/
    ├── sphinx_ext/
    ├── lsp/
    └── cli/
```

## Common Commands

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=archml

# Run a specific test file or test
uv run pytest tests/parser/test_lexer.py
uv run pytest -k "test_parse_component"

# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Type check
uv run ty check src/

# Build the package
uv build

# Build Sphinx docs
uv run sphinx-build docs/sphinx docs/sphinx/_build
```

## Development Methodology

Every new feature requires thorough testing before it is considered complete. The workflow is:

1. Write or update the relevant specification/design if needed.
2. Implement the feature in `src/archml/`.
3. Write tests in `tests/` covering normal cases, edge cases, and error cases.
4. Ensure all tests pass, ruff reports no issues, and ty finds no type errors.
5. Commit with a clear message describing the change.

Tests are not optional. A feature without tests is not done.

## ArchML Language Quick Reference

The DSL defines architecture through these core constructs:

- **`system`** — groups components or sub-systems
- **`component`** — module with `requires` and `provides` interface declarations; supports nesting
- **`interface`** — typed contract between elements; supports versioning (`@v1`, `@v2`)
- **`type`** — reusable data structure used within interfaces
- **`enum`** — constrained set of named values
- **`connect`** — data-flow edge linking a required interface to a provided interface (`->`)
- **`external`** — marks a system or component as outside the development boundary
- **`import` / `use`** — multi-file composition; `use` always includes the entity type (e.g., `use component X`)
- **`tags`** — arbitrary labels for filtering and view generation
- **`field`** — typed data element with optional `description` and `schema` annotations

Primitive types: `String`, `Int`, `Float`, `Decimal`, `Bool`, `Bytes`, `Timestamp`, `Datetime`
Container types: `List<T>`, `Map<K, V>`, `Optional<T>`
Filesystem types: `File` (with `filetype`, `schema`), `Directory` (with `schema`)

Full syntax specification: `docs/LANGUAGE_SYNTAX.md`

## Architecture and Design Decisions

- The parser produces an AST which is then lowered into a semantic model. Validation runs on the semantic model, not the AST.
- Views are not part of the architecture language. They will be defined in a separate view DSL that references model entities.
- The Sphinx extension reads `.archml` files directly and renders views inline — it is not an export pipeline.
- The CLI is the primary user entry point for parsing, validating, and generating views outside of Sphinx.
- A Language Server Protocol (LSP) implementation provides IDE support (diagnostics, completion, go-to-definition) for `.archml` files, with a VS Code extension as the primary client.

## Coding Conventions

- Use `ruff` defaults for formatting and linting rules.
- All public APIs must have type annotations.
- Prefer dataclasses or attrs for model types.
- Keep modules focused: one responsibility per module.
- The test directory structure mirrors the source structure. Every module in `src/archml/<package>/` has a corresponding directory in `tests/<package>/`. Test files are prefixed with `test_`: `src/archml/parser/lexer.py` -> `tests/parser/test_lexer.py`.
- Every Python file follows this layout:

```python
# Copyright ...
# SPDX-License-Identifier: Apache-2.0

import ...

# ###############
# Public Interface
# ###############

def public_function() -> None:
    """Docstring describing the function."""
    ...

# ################
# Implementation
# ################

def _private_helper() -> None:
    ...
```

The copyright header and imports come first. Public interface (classes, functions, constants) is separated from private implementation by section comments. All private members are prefixed with an underscore.
