# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Recursive-descent parser for .archml files.

Converts a token stream produced by the scanner into an ArchFile semantic model.
"""

from archml.compiler.scanner import Token, TokenType, tokenize
from archml.model.entities import (
    ArchFile,
    ArtifactDef,
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

# ###############
# Public Interface
# ###############


class ParseError(Exception):
    """Raised when the parser encounters a syntactically invalid construct.

    Attributes:
        filename: Source file path (empty string when not provided).
        line: 1-based line number of the error.
        column: 1-based column number of the error.
    """

    def __init__(self, message: str, line: int, column: int, filename: str = "") -> None:
        loc = f"{filename}:{line}:{column}" if filename else f"{line}:{column}"
        super().__init__(f"{loc}: {message}")
        self.filename = filename
        self.line = line
        self.column = column


def parse(source: str, filename: str = "") -> ArchFile:
    """Parse ArchML source text into a semantic ArchFile model.

    Args:
        source: The full text of an .archml file.
        filename: Optional source file path included in error messages.

    Returns:
        An ArchFile instance representing the parsed architecture.

    Raises:
        LexerError: If the source contains invalid characters or unterminated literals.
        ParseError: If the source is syntactically invalid.
    """
    tokens = tokenize(source, filename)
    return _Parser(tokens, filename).parse()


# ################
# Implementation
# ################

_KEYWORD_TYPES: frozenset[TokenType] = frozenset(
    {
        TokenType.SYSTEM,
        TokenType.COMPONENT,
        TokenType.USER,
        TokenType.INTERFACE,
        TokenType.CONNECT,
        TokenType.EXPOSE,
        TokenType.TYPE,
        TokenType.ENUM,
        TokenType.REQUIRES,
        TokenType.PROVIDES,
        TokenType.AS,
        TokenType.FROM,
        TokenType.IMPORT,
        TokenType.USE,
        TokenType.EXTERNAL,
        TokenType.ARTIFACT,
    }
)

_PRIMITIVE_TYPES: dict[str, PrimitiveType] = {
    "String": PrimitiveType.STRING,
    "Int": PrimitiveType.INT,
    "Float": PrimitiveType.FLOAT,
    "Bool": PrimitiveType.BOOL,
    "Bytes": PrimitiveType.BYTES,
    "Timestamp": PrimitiveType.TIMESTAMP,
    "Datetime": PrimitiveType.DATETIME,
}


class _Parser:
    """Recursive-descent parser for ArchML token streams."""

    def __init__(self, tokens: list[Token], filename: str = "") -> None:
        self._tokens = tokens
        self._pos = 0
        self._filename = filename

    def parse(self) -> ArchFile:
        """Parse the full token stream and return an ArchFile."""
        result = ArchFile()
        while not self._at_end():
            self._parse_top_level(result)
        return result

    # ------------------------------------------------------------------
    # Token access helpers
    # ------------------------------------------------------------------

    def _current(self) -> Token:
        """Return the current (un-consumed) token."""
        return self._tokens[self._pos]

    def _peek_type(self) -> TokenType:
        """Return the token type of the current token."""
        return self._tokens[self._pos].type

    def _peek_type_at(self, offset: int) -> TokenType:
        """Return the token type at position self._pos + offset (clamped to EOF)."""
        idx = self._pos + offset
        if idx >= len(self._tokens):
            return TokenType.EOF
        return self._tokens[idx].type

    def _at_end(self) -> bool:
        """Return True if the current token is the EOF token."""
        return self._peek_type() == TokenType.EOF

    def _advance(self) -> Token:
        """Consume and return the current token, stopping at EOF."""
        tok = self._tokens[self._pos]
        if self._pos < len(self._tokens) - 1:
            self._pos += 1
        return tok

    def _expect(self, *types: TokenType) -> Token:
        """Consume the current token if it matches any of the given types.

        Raises ParseError if the current token does not match.
        """
        tok = self._current()
        if tok.type not in types:
            expected = ", ".join(repr(t.value) for t in types)
            raise ParseError(
                f"Expected {expected}, got {tok.value!r}",
                tok.line,
                tok.column,
                self._filename,
            )
        return self._advance()

    def _check(self, *types: TokenType) -> bool:
        """Return True if the current token matches any of the given types (without
        consuming).
        """
        return self._peek_type() in types

    def _expect_name_token(self) -> Token:
        """Consume the current token as a name.

        Accepts identifiers and keywords used in name positions (e.g. a field
        named 'as').  Raises ParseError for structural tokens and EOF.
        """
        tok = self._current()
        if tok.type != TokenType.IDENTIFIER and tok.type not in _KEYWORD_TYPES:
            raise ParseError(
                f"Expected identifier, got {tok.value!r}",
                tok.line,
                tok.column,
                self._filename,
            )
        return self._advance()

    # ------------------------------------------------------------------
    # Top-level declarations
    # ------------------------------------------------------------------

    def _parse_top_level(self, result: ArchFile) -> None:
        """Parse one top-level declaration and append it to the ArchFile."""
        tok = self._current()
        if tok.type == TokenType.FROM:
            result.imports.append(self._parse_import())
        elif tok.type == TokenType.ENUM:
            result.enums.append(self._parse_enum())
        elif tok.type == TokenType.TYPE:
            result.types.append(self._parse_type_def())
        elif tok.type == TokenType.ARTIFACT:
            result.artifacts.append(self._parse_artifact_def())
        elif tok.type == TokenType.INTERFACE:
            result.interfaces.append(self._parse_interface(parent_variants=[]))
        elif tok.type == TokenType.COMPONENT:
            result.components.append(self._parse_component(is_external=False, parent_variants=[]))
        elif tok.type == TokenType.SYSTEM:
            result.systems.append(self._parse_system(is_external=False, parent_variants=[]))
        elif tok.type == TokenType.USER:
            result.users.append(self._parse_user(is_external=False, parent_variants=[]))
        elif tok.type == TokenType.CONNECT:
            result.connects.append(self._parse_connect())
        elif tok.type == TokenType.EXTERNAL:
            self._advance()  # consume 'external'
            inner = self._current()
            if inner.type == TokenType.COMPONENT:
                result.components.append(self._parse_component(is_external=True, parent_variants=[]))
            elif inner.type == TokenType.SYSTEM:
                result.systems.append(self._parse_system(is_external=True, parent_variants=[]))
            elif inner.type == TokenType.USER:
                result.users.append(self._parse_user(is_external=True, parent_variants=[]))
            else:
                raise ParseError(
                    f"Expected 'component', 'system', or 'user' after 'external', got {inner.value!r}",
                    inner.line,
                    inner.column,
                    self._filename,
                )
        else:
            raise ParseError(
                f"Unexpected token {tok.value!r} at top level",
                tok.line,
                tok.column,
                self._filename,
            )

    # ------------------------------------------------------------------
    # Import declarations
    # ------------------------------------------------------------------

    def _parse_import(self) -> ImportDeclaration:
        """Parse: from <path> import <entity1> [, <entity2>]*"""
        from_tok = self._expect(TokenType.FROM)
        path = self._parse_import_path()
        self._expect(TokenType.IMPORT)
        entities = self._parse_identifier_list()
        return ImportDeclaration(source_path=path, entities=entities, line=from_tok.line)

    def _parse_import_path(self) -> str:
        """Parse an import path such as 'interfaces/order' or '@repo/path/to/file'."""
        parts: list[str] = []
        # Optional cross-repo prefix: @repo
        if self._check(TokenType.AT):
            self._advance()  # consume @
            repo_tok = self._expect(TokenType.IDENTIFIER)
            self._expect(TokenType.SLASH)
            parts.append(f"@{repo_tok.value}")
        # Main path: identifier (/ identifier)*
        first = self._expect(TokenType.IDENTIFIER)
        parts.append(first.value)
        while self._check(TokenType.SLASH):
            self._advance()  # consume /
            seg = self._expect(TokenType.IDENTIFIER)
            parts.append(seg.value)
        return "/".join(parts)

    def _parse_identifier_list(self) -> list[str]:
        """Parse a comma-separated list of identifiers."""
        names: list[str] = []
        first = self._expect(TokenType.IDENTIFIER)
        names.append(first.value)
        while self._check(TokenType.COMMA):
            self._advance()  # consume ,
            name = self._expect(TokenType.IDENTIFIER)
            names.append(name.value)
        return names

    # ------------------------------------------------------------------
    # Enum declarations
    # ------------------------------------------------------------------

    def _parse_enum(self) -> EnumDef:
        """Parse: enum <Name> { [\"\"\"docstring\"\"\"] [@attr: val, ...]* <Value>* }

        An optional triple-quoted docstring may appear as the first item in the
        body.  Each enum value must appear on its own line (line number strictly
        greater than the opening brace or the previous value).
        """
        self._expect(TokenType.ENUM)
        name_tok = self._expect(TokenType.IDENTIFIER)
        lbrace = self._expect(TokenType.LBRACE)
        enum_def = EnumDef(name=name_tok.value, line=name_tok.line)
        if self._check(TokenType.TRIPLE_STRING):
            enum_def.description = self._advance().value
        while self._check(TokenType.AT):
            attr_name, attr_values = self._parse_attribute()
            enum_def.attributes[attr_name] = attr_values
        last_value_line = lbrace.line
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.TRIPLE_STRING):
                tok = self._current()
                raise ParseError(
                    "Description docstring must appear first in body",
                    tok.line,
                    tok.column,
                    self._filename,
                )
            elif self._check(TokenType.IDENTIFIER):
                value_tok = self._current()
                if value_tok.line <= last_value_line:
                    raise ParseError(
                        f"Enum value {value_tok.value!r} must be on a new line",
                        value_tok.line,
                        value_tok.column,
                        self._filename,
                    )
                last_value_line = value_tok.line
                self._advance()
                enum_def.values.append(value_tok.value)
            else:
                tok = self._current()
                raise ParseError(
                    f"Unexpected token {tok.value!r} in enum body",
                    tok.line,
                    tok.column,
                    self._filename,
                )
        self._expect(TokenType.RBRACE)
        return enum_def

    # ------------------------------------------------------------------
    # Type declarations
    # ------------------------------------------------------------------

    def _parse_type_def(self) -> TypeDef:
        """Parse: type <Name> { [\"\"\"docstring\"\"\"] [@attr: val, ...]* field* }"""
        self._expect(TokenType.TYPE)
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LBRACE)
        type_def = TypeDef(name=name_tok.value, line=name_tok.line)
        if self._check(TokenType.TRIPLE_STRING):
            type_def.description = self._advance().value
        while self._check(TokenType.AT):
            attr_name, attr_values = self._parse_attribute()
            type_def.attributes[attr_name] = attr_values
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.TRIPLE_STRING):
                tok = self._current()
                raise ParseError(
                    "Description docstring must appear first in body",
                    tok.line,
                    tok.column,
                    self._filename,
                )
            elif self._at_field_start():
                type_def.fields.append(self._parse_field())
            else:
                tok = self._current()
                raise ParseError(
                    f"Unexpected token {tok.value!r} in type body",
                    tok.line,
                    tok.column,
                    self._filename,
                )
        self._expect(TokenType.RBRACE)
        return type_def

    # ------------------------------------------------------------------
    # Artifact declarations
    # ------------------------------------------------------------------

    def _parse_artifact_def(self) -> ArtifactDef:
        """Parse: artifact <Name> { [\"\"\"docstring\"\"\"] [@attr: val, ...]* }"""
        self._expect(TokenType.ARTIFACT)
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LBRACE)
        artifact = ArtifactDef(name=name_tok.value, line=name_tok.line)
        if self._check(TokenType.TRIPLE_STRING):
            artifact.description = self._advance().value
        while self._check(TokenType.AT):
            attr_name, attr_values = self._parse_attribute()
            artifact.attributes[attr_name] = attr_values
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            tok = self._current()
            if self._check(TokenType.TRIPLE_STRING):
                raise ParseError(
                    "Description docstring must appear first in body",
                    tok.line,
                    tok.column,
                    self._filename,
                )
            raise ParseError(
                f"Unexpected token {tok.value!r} in artifact body",
                tok.line,
                tok.column,
                self._filename,
            )
        self._expect(TokenType.RBRACE)
        return artifact

    # ------------------------------------------------------------------
    # Interface declarations
    # ------------------------------------------------------------------

    def _parse_interface(self, parent_variants: list[str]) -> InterfaceDef:
        """Parse: interface[<v1, v2>] <Name> { [\"\"\"docstring\"\"\"] [@attr: val, ...]* field* }"""
        self._expect(TokenType.INTERFACE)
        own_variants = self._parse_variant_annotation()
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LBRACE)
        iface = InterfaceDef(
            name=name_tok.value,
            variants=_union_variants(parent_variants, own_variants),
            line=name_tok.line,
        )
        if self._check(TokenType.TRIPLE_STRING):
            iface.description = self._advance().value
        while self._check(TokenType.AT):
            attr_name, attr_values = self._parse_attribute()
            iface.attributes[attr_name] = attr_values
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.TRIPLE_STRING):
                tok = self._current()
                raise ParseError(
                    "Description docstring must appear first in body",
                    tok.line,
                    tok.column,
                    self._filename,
                )
            elif self._at_field_start():
                iface.fields.append(self._parse_field())
            else:
                tok = self._current()
                raise ParseError(
                    f"Unexpected token {tok.value!r} in interface body",
                    tok.line,
                    tok.column,
                    self._filename,
                )
        self._expect(TokenType.RBRACE)
        return iface

    # ------------------------------------------------------------------
    # Component declarations
    # ------------------------------------------------------------------

    def _parse_component(self, is_external: bool, parent_variants: list[str]) -> Component:
        """Parse: [external] component[<v1, v2>] <Name> { [\"\"\"docstring\"\"\"] ... }"""
        self._expect(TokenType.COMPONENT)
        own_variants = self._parse_variant_annotation()
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LBRACE)
        effective_variants = _union_variants(parent_variants, own_variants)
        comp = Component(
            name=name_tok.value,
            is_external=is_external,
            variants=effective_variants,
            line=name_tok.line,
        )
        if self._check(TokenType.TRIPLE_STRING):
            comp.description = self._advance().value
        while self._check(TokenType.AT):
            attr_name, attr_values = self._parse_attribute()
            comp.attributes[attr_name] = attr_values
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.TRIPLE_STRING):
                tok = self._current()
                raise ParseError(
                    "Description docstring must appear first in body",
                    tok.line,
                    tok.column,
                    self._filename,
                )
            elif self._check(TokenType.REQUIRES):
                comp.requires.append(self._parse_interface_ref(TokenType.REQUIRES))
            elif self._check(TokenType.PROVIDES):
                comp.provides.append(self._parse_interface_ref(TokenType.PROVIDES))
            elif self._check(TokenType.INTERFACE):
                comp.interfaces.append(self._parse_interface(parent_variants=effective_variants))
            elif self._check(TokenType.COMPONENT):
                comp.components.append(self._parse_component(is_external=False, parent_variants=effective_variants))
            elif self._check(TokenType.CONNECT):
                comp.connects.append(self._parse_connect())
            elif self._check(TokenType.EXPOSE):
                comp.exposes.append(self._parse_expose())
            elif self._check(TokenType.EXTERNAL):
                self._advance()  # consume 'external'
                inner = self._current()
                if inner.type == TokenType.COMPONENT:
                    comp.components.append(self._parse_component(is_external=True, parent_variants=effective_variants))
                else:
                    raise ParseError(
                        f"Expected 'component' after 'external' inside component body, got {inner.value!r}",
                        inner.line,
                        inner.column,
                        self._filename,
                    )
            else:
                tok = self._current()
                raise ParseError(
                    f"Unexpected token {tok.value!r} in component body",
                    tok.line,
                    tok.column,
                    self._filename,
                )
        self._expect(TokenType.RBRACE)
        return comp

    # ------------------------------------------------------------------
    # System declarations
    # ------------------------------------------------------------------

    def _parse_system(self, is_external: bool, parent_variants: list[str]) -> System:
        """Parse: [external] system[<v1, v2>] <Name> { [\"\"\"docstring\"\"\"] ... }"""
        self._expect(TokenType.SYSTEM)
        own_variants = self._parse_variant_annotation()
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LBRACE)
        effective_variants = _union_variants(parent_variants, own_variants)
        system = System(
            name=name_tok.value,
            is_external=is_external,
            variants=effective_variants,
            line=name_tok.line,
        )
        if self._check(TokenType.TRIPLE_STRING):
            system.description = self._advance().value
        while self._check(TokenType.AT):
            attr_name, attr_values = self._parse_attribute()
            system.attributes[attr_name] = attr_values
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.TRIPLE_STRING):
                tok = self._current()
                raise ParseError(
                    "Description docstring must appear first in body",
                    tok.line,
                    tok.column,
                    self._filename,
                )
            elif self._check(TokenType.REQUIRES):
                system.requires.append(self._parse_interface_ref(TokenType.REQUIRES))
            elif self._check(TokenType.PROVIDES):
                system.provides.append(self._parse_interface_ref(TokenType.PROVIDES))
            elif self._check(TokenType.INTERFACE):
                system.interfaces.append(self._parse_interface(parent_variants=effective_variants))
            elif self._check(TokenType.COMPONENT):
                system.components.append(self._parse_component(is_external=False, parent_variants=effective_variants))
            elif self._check(TokenType.SYSTEM):
                system.systems.append(self._parse_system(is_external=False, parent_variants=effective_variants))
            elif self._check(TokenType.USER):
                system.users.append(self._parse_user(is_external=False, parent_variants=effective_variants))
            elif self._check(TokenType.CONNECT):
                system.connects.append(self._parse_connect())
            elif self._check(TokenType.EXPOSE):
                system.exposes.append(self._parse_expose())
            elif self._check(TokenType.EXTERNAL):
                self._advance()  # consume 'external'
                inner = self._current()
                if inner.type == TokenType.COMPONENT:
                    system.components.append(
                        self._parse_component(is_external=True, parent_variants=effective_variants)
                    )
                elif inner.type == TokenType.SYSTEM:
                    system.systems.append(self._parse_system(is_external=True, parent_variants=effective_variants))
                elif inner.type == TokenType.USER:
                    system.users.append(self._parse_user(is_external=True, parent_variants=effective_variants))
                else:
                    raise ParseError(
                        f"Expected 'component', 'system', or 'user' after 'external'"
                        f" inside system body, got {inner.value!r}",
                        inner.line,
                        inner.column,
                        self._filename,
                    )
            elif self._check(TokenType.USE):
                entity = self._parse_use_statement(parent_variants=effective_variants)
                _append_to_system(system, entity)
            else:
                tok = self._current()
                raise ParseError(
                    f"Unexpected token {tok.value!r} in system body",
                    tok.line,
                    tok.column,
                    self._filename,
                )
        self._expect(TokenType.RBRACE)
        return system

    def _parse_use_statement(self, parent_variants: list[str]) -> Component | System | UserDef:
        """Parse: use component <Name> | use system <Name> | use user <Name>.

        The stub entity inherits the parent scope's variant context.
        """
        self._expect(TokenType.USE)
        kind = self._current()
        if kind.type == TokenType.COMPONENT:
            self._advance()
            name_tok = self._expect(TokenType.IDENTIFIER)
            return Component(name=name_tok.value, is_stub=True, variants=list(parent_variants), line=name_tok.line)
        elif kind.type == TokenType.SYSTEM:
            self._advance()
            name_tok = self._expect(TokenType.IDENTIFIER)
            return System(name=name_tok.value, is_stub=True, variants=list(parent_variants), line=name_tok.line)
        elif kind.type == TokenType.USER:
            self._advance()
            name_tok = self._expect(TokenType.IDENTIFIER)
            return UserDef(name=name_tok.value, variants=list(parent_variants), line=name_tok.line)
        else:
            raise ParseError(
                f"Expected 'component', 'system', or 'user' after 'use', got {kind.value!r}",
                kind.line,
                kind.column,
                self._filename,
            )

    # ------------------------------------------------------------------
    # User declarations
    # ------------------------------------------------------------------

    def _parse_user(self, is_external: bool, parent_variants: list[str]) -> UserDef:
        """Parse: [external] user[<v1, v2>] <Name> { [\"\"\"docstring\"\"\"] [@attr: val, ...]* (requires|provides)* }

        Users are leaf nodes: they support an optional docstring, attributes,
        variant annotation, requires, and provides, but no sub-entities or channels.
        """
        self._expect(TokenType.USER)
        own_variants = self._parse_variant_annotation()
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LBRACE)
        user = UserDef(
            name=name_tok.value,
            is_external=is_external,
            variants=_union_variants(parent_variants, own_variants),
            line=name_tok.line,
        )
        if self._check(TokenType.TRIPLE_STRING):
            user.description = self._advance().value
        while self._check(TokenType.AT):
            attr_name, attr_values = self._parse_attribute()
            user.attributes[attr_name] = attr_values
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.TRIPLE_STRING):
                tok = self._current()
                raise ParseError(
                    "Description docstring must appear first in body",
                    tok.line,
                    tok.column,
                    self._filename,
                )
            elif self._check(TokenType.REQUIRES):
                user.requires.append(self._parse_interface_ref(TokenType.REQUIRES))
            elif self._check(TokenType.PROVIDES):
                user.provides.append(self._parse_interface_ref(TokenType.PROVIDES))
            else:
                tok = self._current()
                raise ParseError(
                    f"Unexpected token {tok.value!r} in user body",
                    tok.line,
                    tok.column,
                    self._filename,
                )
        self._expect(TokenType.RBRACE)
        return user

    # ------------------------------------------------------------------
    # Connect statements
    # ------------------------------------------------------------------

    def _parse_connect(self) -> ConnectDef:
        """Parse a connect statement.

        Four forms:
            connect[<v1, v2>] <src_port> -> $<channel> -> <dst_port>
            connect[<v1, v2>] <src_port> -> $<channel>
            connect[<v1, v2>] $<channel> -> <dst_port>
            connect[<v1, v2>] <src_port> -> <dst_port>

        Where <src_port> / <dst_port> is either ``Entity.port`` or just
        ``port`` (port on the current scope's own boundary).
        """
        connect_tok = self._expect(TokenType.CONNECT)
        variants = self._parse_variant_annotation()
        connect_def = ConnectDef(variants=variants, line=connect_tok.line)

        # Parse left-hand side: either $channel or Entity.port / port
        if self._check(TokenType.DOLLAR):
            # Form: connect $channel -> <dst_port>
            self._advance()  # consume $
            ch_tok = self._expect(TokenType.IDENTIFIER)
            connect_def = ConnectDef(channel=ch_tok.value, variants=variants, line=connect_tok.line)
            self._expect(TokenType.ARROW)
            entity, port = self._parse_port_ref(connect_tok)
            connect_def = ConnectDef(
                channel=ch_tok.value,
                dst_entity=entity,
                dst_port=port,
                variants=variants,
                line=connect_tok.line,
            )
        else:
            # Left side is a port reference
            src_entity, src_port = self._parse_port_ref(connect_tok)
            self._expect(TokenType.ARROW)

            if self._check(TokenType.DOLLAR):
                # Form: connect <src_port> -> $channel [-> <dst_port>]
                self._advance()  # consume $
                ch_tok = self._expect(TokenType.IDENTIFIER)
                if self._check(TokenType.ARROW):
                    self._advance()  # consume ->
                    dst_entity, dst_port = self._parse_port_ref(connect_tok)
                    connect_def = ConnectDef(
                        src_entity=src_entity,
                        src_port=src_port,
                        channel=ch_tok.value,
                        dst_entity=dst_entity,
                        dst_port=dst_port,
                        variants=variants,
                        line=connect_tok.line,
                    )
                else:
                    # One-sided src
                    connect_def = ConnectDef(
                        src_entity=src_entity,
                        src_port=src_port,
                        channel=ch_tok.value,
                        variants=variants,
                        line=connect_tok.line,
                    )
            else:
                # Direct: connect <src_port> -> <dst_port>
                dst_entity, dst_port = self._parse_port_ref(connect_tok)
                connect_def = ConnectDef(
                    src_entity=src_entity,
                    src_port=src_port,
                    dst_entity=dst_entity,
                    dst_port=dst_port,
                    variants=variants,
                    line=connect_tok.line,
                )

        return connect_def

    def _parse_port_ref(self, ctx_tok: Token) -> tuple[str | None, str]:
        """Parse a port reference: ``Entity.port`` or just ``port``.

        Returns a tuple ``(entity_name_or_None, port_name)``.
        """
        name_tok = self._expect(TokenType.IDENTIFIER)
        if self._check(TokenType.DOT):
            self._advance()  # consume .
            port_tok = self._expect(TokenType.IDENTIFIER)
            return (name_tok.value, port_tok.value)
        return (None, name_tok.value)

    # ------------------------------------------------------------------
    # Expose statements
    # ------------------------------------------------------------------

    def _parse_expose(self) -> ExposeDef:
        """Parse: expose[<v1, v2>] <Entity>.<port> [as <new_name>]"""
        expose_tok = self._expect(TokenType.EXPOSE)
        variants = self._parse_variant_annotation()
        entity_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.DOT)
        port_tok = self._expect(TokenType.IDENTIFIER)
        as_name: str | None = None
        if self._check(TokenType.AS):
            self._advance()  # consume 'as'
            as_tok = self._expect(TokenType.IDENTIFIER)
            as_name = as_tok.value
        return ExposeDef(
            entity=entity_tok.value,
            port=port_tok.value,
            as_name=as_name,
            variants=variants,
            line=expose_tok.line,
        )

    # ------------------------------------------------------------------
    # Field declarations
    # ------------------------------------------------------------------

    def _at_field_start(self) -> bool:
        """Return True if the current position looks like the start of a field def.

        A field starts with any name token (identifier or keyword) followed by a colon.
        """
        cur = self._peek_type()
        if cur != TokenType.IDENTIFIER and cur not in _KEYWORD_TYPES:
            return False
        return self._peek_type_at(1) == TokenType.COLON

    def _parse_field(self) -> FieldDef:
        """Parse: <name>: <type>"""
        name_tok = self._expect_name_token()
        self._expect(TokenType.COLON)
        field_type = self._parse_type_ref()
        return FieldDef(name=name_tok.value, type=field_type, line=name_tok.line)

    # ------------------------------------------------------------------
    # Type references
    # ------------------------------------------------------------------

    def _parse_type_ref(self) -> TypeRef:
        """Parse a type reference.

        Handles primitive types, List<T>, Map<K,V>, Optional<T>, or a named type.
        """
        name_tok = self._expect(TokenType.IDENTIFIER)
        name = name_tok.value
        if name in _PRIMITIVE_TYPES:
            return PrimitiveTypeRef(primitive=_PRIMITIVE_TYPES[name])
        if name == "List":
            self._expect(TokenType.LANGLE)
            inner = self._parse_type_ref()
            self._expect(TokenType.RANGLE)
            return ListTypeRef(element_type=inner)
        if name == "Map":
            self._expect(TokenType.LANGLE)
            key = self._parse_type_ref()
            self._expect(TokenType.COMMA)
            value = self._parse_type_ref()
            self._expect(TokenType.RANGLE)
            return MapTypeRef(key_type=key, value_type=value)
        if name == "Optional":
            self._expect(TokenType.LANGLE)
            inner = self._parse_type_ref()
            self._expect(TokenType.RANGLE)
            return OptionalTypeRef(inner_type=inner)
        return NamedTypeRef(name=name)

    # ------------------------------------------------------------------
    # Interface references (requires / provides)
    # ------------------------------------------------------------------

    def _parse_interface_ref(self, keyword: TokenType) -> InterfaceRef:
        """Parse: requires/provides[<v1, v2>] <Name> [as <port_name>]"""
        self._expect(keyword)
        variants = self._parse_variant_annotation()
        name_tok = self._expect(TokenType.IDENTIFIER)
        port_name: str | None = None
        if self._check(TokenType.AS):
            self._advance()  # consume 'as'
            alias_tok = self._expect(TokenType.IDENTIFIER)
            port_name = alias_tok.value
        return InterfaceRef(name=name_tok.value, port_name=port_name, variants=variants, line=name_tok.line)

    # ------------------------------------------------------------------
    # Variant annotation and attribute parsers
    # ------------------------------------------------------------------

    def _parse_variant_annotation(self) -> list[str]:
        """Parse an optional inline variant annotation: [<id1, id2, ...>].

        Returns the list of variant names, or an empty list if no annotation
        is present.
        """
        if not self._check(TokenType.LANGLE):
            return []
        self._advance()  # consume <
        variants: list[str] = []
        first = self._expect(TokenType.IDENTIFIER)
        variants.append(first.value)
        while self._check(TokenType.COMMA):
            self._advance()  # consume ,
            v = self._expect(TokenType.IDENTIFIER)
            variants.append(v.value)
        self._expect(TokenType.RANGLE)
        return variants

    def _parse_attribute(self) -> tuple[str, list[str]]:
        """Parse a custom attribute line: @<name>: <id1>, <id2>, ...

        Returns a tuple of (attribute_name, [value, ...]).
        """
        self._expect(TokenType.AT)
        name_tok = self._expect_name_token()
        self._expect(TokenType.COLON)
        values: list[str] = []
        first = self._expect_name_token()
        values.append(first.value)
        while self._check(TokenType.COMMA):
            self._advance()  # consume ,
            v = self._expect_name_token()
            values.append(v.value)
        return name_tok.value, values


# ################
# Module-level helpers
# ################


def _union_variants(parent: list[str], own: list[str]) -> list[str]:
    """Return the union of *parent* and *own* variant sets, preserving order."""
    result = list(parent)
    for v in own:
        if v not in result:
            result.append(v)
    return result


def _append_to_system(system: System, entity: Component | System | UserDef) -> None:
    """Append a use-statement entity to the correct collection on *system*."""
    if isinstance(entity, Component):
        system.components.append(entity)
    elif isinstance(entity, System):
        system.systems.append(entity)
    else:
        system.users.append(entity)
