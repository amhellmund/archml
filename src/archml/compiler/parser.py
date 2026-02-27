# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Recursive-descent parser for .archml files.

Converts a token stream produced by the scanner into an ArchFile semantic model.
"""

from archml.compiler.scanner import Token, TokenType, tokenize
from archml.model.entities import (
    ArchFile,
    Component,
    Connection,
    ConnectionEndpoint,
    EnumDef,
    ImportDeclaration,
    InterfaceDef,
    InterfaceRef,
    System,
    TypeDef,
)
from archml.model.types import (
    DirectoryTypeRef,
    Field,
    FileTypeRef,
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
        line: 1-based line number of the error.
        column: 1-based column number of the error.
    """

    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__(f"Line {line}, column {column}: {message}")
        self.line = line
        self.column = column


def parse(source: str) -> ArchFile:
    """Parse ArchML source text into a semantic ArchFile model.

    Args:
        source: The full text of an .archml file.

    Returns:
        An ArchFile instance representing the parsed architecture.

    Raises:
        LexerError: If the source contains invalid characters or unterminated literals.
        ParseError: If the source is syntactically invalid.
    """
    tokens = tokenize(source)
    return _Parser(tokens).parse()


# ################
# Implementation
# ################

_KEYWORD_TYPES: frozenset[TokenType] = frozenset(
    {
        TokenType.SYSTEM,
        TokenType.COMPONENT,
        TokenType.INTERFACE,
        TokenType.TYPE,
        TokenType.ENUM,
        TokenType.FIELD,
        TokenType.FILETYPE,
        TokenType.SCHEMA,
        TokenType.REQUIRES,
        TokenType.PROVIDES,
        TokenType.CONNECT,
        TokenType.BY,
        TokenType.FROM,
        TokenType.IMPORT,
        TokenType.USE,
        TokenType.EXTERNAL,
        TokenType.TAGS,
        TokenType.TITLE,
        TokenType.DESCRIPTION,
        TokenType.TRUE,
        TokenType.FALSE,
    }
)

_PRIMITIVE_TYPES: dict[str, PrimitiveType] = {
    "String": PrimitiveType.STRING,
    "Int": PrimitiveType.INT,
    "Float": PrimitiveType.FLOAT,
    "Decimal": PrimitiveType.DECIMAL,
    "Bool": PrimitiveType.BOOL,
    "Bytes": PrimitiveType.BYTES,
    "Timestamp": PrimitiveType.TIMESTAMP,
    "Datetime": PrimitiveType.DATETIME,
}


class _Parser:
    """Recursive-descent parser for ArchML token streams."""

    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._pos = 0

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
        named 'by').  Raises ParseError for structural tokens and EOF.
        """
        tok = self._current()
        if tok.type != TokenType.IDENTIFIER and tok.type not in _KEYWORD_TYPES:
            raise ParseError(
                f"Expected identifier, got {tok.value!r}",
                tok.line,
                tok.column,
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
        elif tok.type == TokenType.INTERFACE:
            result.interfaces.append(self._parse_interface())
        elif tok.type == TokenType.COMPONENT:
            result.components.append(self._parse_component(is_external=False))
        elif tok.type == TokenType.SYSTEM:
            result.systems.append(self._parse_system(is_external=False))
        elif tok.type == TokenType.EXTERNAL:
            self._advance()  # consume 'external'
            inner = self._current()
            if inner.type == TokenType.COMPONENT:
                result.components.append(self._parse_component(is_external=True))
            elif inner.type == TokenType.SYSTEM:
                result.systems.append(self._parse_system(is_external=True))
            else:
                raise ParseError(
                    f"Expected 'component' or 'system' after 'external', got {inner.value!r}",
                    inner.line,
                    inner.column,
                )
        else:
            raise ParseError(
                f"Unexpected token {tok.value!r} at top level",
                tok.line,
                tok.column,
            )

    # ------------------------------------------------------------------
    # Import declarations
    # ------------------------------------------------------------------

    def _parse_import(self) -> ImportDeclaration:
        """Parse: from <path> import <entity1> [, <entity2>]*"""
        self._expect(TokenType.FROM)
        path = self._parse_import_path()
        self._expect(TokenType.IMPORT)
        entities = self._parse_identifier_list()
        return ImportDeclaration(source_path=path, entities=entities)

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
        """Parse: enum <Name> { [attrs] <Value>* }"""
        self._expect(TokenType.ENUM)
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LBRACE)
        enum_def = EnumDef(name=name_tok.value)
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.TITLE):
                enum_def.title = self._parse_string_attr(TokenType.TITLE)
            elif self._check(TokenType.DESCRIPTION):
                enum_def.description = self._parse_string_attr(TokenType.DESCRIPTION)
            elif self._check(TokenType.TAGS):
                enum_def.tags = self._parse_tags()
            elif self._check(TokenType.IDENTIFIER):
                value_tok = self._advance()
                enum_def.values.append(value_tok.value)
            else:
                tok = self._current()
                raise ParseError(
                    f"Unexpected token {tok.value!r} in enum body",
                    tok.line,
                    tok.column,
                )
        self._expect(TokenType.RBRACE)
        return enum_def

    # ------------------------------------------------------------------
    # Type declarations
    # ------------------------------------------------------------------

    def _parse_type_def(self) -> TypeDef:
        """Parse: type <Name> { [attrs] field* }"""
        self._expect(TokenType.TYPE)
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LBRACE)
        type_def = TypeDef(name=name_tok.value)
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.TITLE):
                type_def.title = self._parse_string_attr(TokenType.TITLE)
            elif self._check(TokenType.DESCRIPTION):
                type_def.description = self._parse_string_attr(TokenType.DESCRIPTION)
            elif self._check(TokenType.TAGS):
                type_def.tags = self._parse_tags()
            elif self._check(TokenType.FIELD):
                type_def.fields.append(self._parse_field())
            else:
                tok = self._current()
                raise ParseError(
                    f"Unexpected token {tok.value!r} in type body",
                    tok.line,
                    tok.column,
                )
        self._expect(TokenType.RBRACE)
        return type_def

    # ------------------------------------------------------------------
    # Interface declarations
    # ------------------------------------------------------------------

    def _parse_interface(self) -> InterfaceDef:
        """Parse: interface <Name> [@version] { [attrs] field* }"""
        self._expect(TokenType.INTERFACE)
        name_tok = self._expect(TokenType.IDENTIFIER)
        version: str | None = None
        if self._check(TokenType.AT):
            self._advance()  # consume @
            ver_tok = self._expect(TokenType.IDENTIFIER)
            version = ver_tok.value
        self._expect(TokenType.LBRACE)
        iface = InterfaceDef(name=name_tok.value, version=version)
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.TITLE):
                iface.title = self._parse_string_attr(TokenType.TITLE)
            elif self._check(TokenType.DESCRIPTION):
                iface.description = self._parse_string_attr(TokenType.DESCRIPTION)
            elif self._check(TokenType.TAGS):
                iface.tags = self._parse_tags()
            elif self._check(TokenType.FIELD):
                iface.fields.append(self._parse_field())
            else:
                tok = self._current()
                raise ParseError(
                    f"Unexpected token {tok.value!r} in interface body",
                    tok.line,
                    tok.column,
                )
        self._expect(TokenType.RBRACE)
        return iface

    # ------------------------------------------------------------------
    # Component declarations
    # ------------------------------------------------------------------

    def _parse_component(self, is_external: bool) -> Component:
        """Parse: [external] component <Name> { ... }"""
        self._expect(TokenType.COMPONENT)
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LBRACE)
        comp = Component(name=name_tok.value, is_external=is_external)
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.TITLE):
                comp.title = self._parse_string_attr(TokenType.TITLE)
            elif self._check(TokenType.DESCRIPTION):
                comp.description = self._parse_string_attr(TokenType.DESCRIPTION)
            elif self._check(TokenType.TAGS):
                comp.tags = self._parse_tags()
            elif self._check(TokenType.REQUIRES):
                comp.requires.append(self._parse_interface_ref(TokenType.REQUIRES))
            elif self._check(TokenType.PROVIDES):
                comp.provides.append(self._parse_interface_ref(TokenType.PROVIDES))
            elif self._check(TokenType.COMPONENT):
                comp.components.append(self._parse_component(is_external=False))
            elif self._check(TokenType.EXTERNAL):
                self._advance()  # consume 'external'
                inner = self._current()
                if inner.type == TokenType.COMPONENT:
                    comp.components.append(self._parse_component(is_external=True))
                else:
                    raise ParseError(
                        f"Expected 'component' after 'external' inside component body, got {inner.value!r}",
                        inner.line,
                        inner.column,
                    )
            elif self._check(TokenType.CONNECT):
                comp.connections.append(self._parse_connection())
            else:
                tok = self._current()
                raise ParseError(
                    f"Unexpected token {tok.value!r} in component body",
                    tok.line,
                    tok.column,
                )
        self._expect(TokenType.RBRACE)
        return comp

    # ------------------------------------------------------------------
    # System declarations
    # ------------------------------------------------------------------

    def _parse_system(self, is_external: bool) -> System:
        """Parse: [external] system <Name> { ... }"""
        self._expect(TokenType.SYSTEM)
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LBRACE)
        system = System(name=name_tok.value, is_external=is_external)
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            if self._check(TokenType.TITLE):
                system.title = self._parse_string_attr(TokenType.TITLE)
            elif self._check(TokenType.DESCRIPTION):
                system.description = self._parse_string_attr(TokenType.DESCRIPTION)
            elif self._check(TokenType.TAGS):
                system.tags = self._parse_tags()
            elif self._check(TokenType.REQUIRES):
                system.requires.append(self._parse_interface_ref(TokenType.REQUIRES))
            elif self._check(TokenType.PROVIDES):
                system.provides.append(self._parse_interface_ref(TokenType.PROVIDES))
            elif self._check(TokenType.COMPONENT):
                system.components.append(self._parse_component(is_external=False))
            elif self._check(TokenType.SYSTEM):
                system.systems.append(self._parse_system(is_external=False))
            elif self._check(TokenType.EXTERNAL):
                self._advance()  # consume 'external'
                inner = self._current()
                if inner.type == TokenType.COMPONENT:
                    system.components.append(self._parse_component(is_external=True))
                elif inner.type == TokenType.SYSTEM:
                    system.systems.append(self._parse_system(is_external=True))
                else:
                    raise ParseError(
                        f"Expected 'component' or 'system' after 'external' inside system body, got {inner.value!r}",
                        inner.line,
                        inner.column,
                    )
            elif self._check(TokenType.USE):
                self._parse_use_statement(system)
            elif self._check(TokenType.CONNECT):
                system.connections.append(self._parse_connection())
            else:
                tok = self._current()
                raise ParseError(
                    f"Unexpected token {tok.value!r} in system body",
                    tok.line,
                    tok.column,
                )
        self._expect(TokenType.RBRACE)
        return system

    def _parse_use_statement(self, system: System) -> None:
        """Parse: use component <Name> | use system <Name>.

        Creates a stub entity in the system. The validation layer resolves
        stubs to their imported definitions.
        """
        self._expect(TokenType.USE)
        kind = self._current()
        if kind.type == TokenType.COMPONENT:
            self._advance()
            name_tok = self._expect(TokenType.IDENTIFIER)
            system.components.append(Component(name=name_tok.value))
        elif kind.type == TokenType.SYSTEM:
            self._advance()
            name_tok = self._expect(TokenType.IDENTIFIER)
            system.systems.append(System(name=name_tok.value))
        else:
            raise ParseError(
                f"Expected 'component' or 'system' after 'use', got {kind.value!r}",
                kind.line,
                kind.column,
            )

    # ------------------------------------------------------------------
    # Connection declarations
    # ------------------------------------------------------------------

    def _parse_connection(self) -> Connection:
        """Parse: connect <source> -> <target> by <interface> [@version] [{ ... }]"""
        self._expect(TokenType.CONNECT)
        source_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.ARROW)
        target_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.BY)
        iface_name_tok = self._expect(TokenType.IDENTIFIER)
        version: str | None = None
        if self._check(TokenType.AT):
            self._advance()
            ver_tok = self._expect(TokenType.IDENTIFIER)
            version = ver_tok.value
        conn = Connection(
            source=ConnectionEndpoint(entity=source_tok.value),
            target=ConnectionEndpoint(entity=target_tok.value),
            interface=InterfaceRef(name=iface_name_tok.value, version=version),
        )
        if self._check(TokenType.LBRACE):
            self._advance()  # consume {
            while not self._check(TokenType.RBRACE, TokenType.EOF):
                self._parse_connection_attr(conn)
            self._expect(TokenType.RBRACE)
        return conn

    def _parse_connection_attr(self, conn: Connection) -> None:
        """Parse a single attribute inside a connection annotation block."""
        tok = self._current()
        if tok.type == TokenType.DESCRIPTION:
            conn.description = self._parse_string_attr(TokenType.DESCRIPTION)
        elif tok.type == TokenType.IDENTIFIER:
            attr_name = self._advance().value
            self._expect(TokenType.EQUALS)
            if attr_name == "protocol":
                str_tok = self._expect(TokenType.STRING)
                conn.protocol = str_tok.value
            elif attr_name == "async":
                bool_tok = self._expect(TokenType.TRUE, TokenType.FALSE)
                conn.is_async = bool_tok.type == TokenType.TRUE
            else:
                raise ParseError(
                    f"Unknown connection attribute {attr_name!r}",
                    tok.line,
                    tok.column,
                )
        else:
            raise ParseError(
                f"Unexpected token {tok.value!r} in connection annotation block",
                tok.line,
                tok.column,
            )

    # ------------------------------------------------------------------
    # Field declarations
    # ------------------------------------------------------------------

    def _parse_field(self) -> Field:
        """Parse: field <name>: <type> [{ description=.. schema=.. filetype=.. }]"""
        self._expect(TokenType.FIELD)
        name_tok = self._expect_name_token()
        self._expect(TokenType.COLON)
        field_type = self._parse_type_ref()
        f = Field(name=name_tok.value, type=field_type)
        if self._check(TokenType.LBRACE):
            self._advance()  # consume {
            while not self._check(TokenType.RBRACE, TokenType.EOF):
                if self._check(TokenType.DESCRIPTION):
                    f.description = self._parse_string_attr(TokenType.DESCRIPTION)
                elif self._check(TokenType.SCHEMA):
                    f.schema = self._parse_string_attr(TokenType.SCHEMA)
                elif self._check(TokenType.FILETYPE):
                    f.filetype = self._parse_string_attr(TokenType.FILETYPE)
                else:
                    inner_tok = self._current()
                    raise ParseError(
                        f"Unexpected token {inner_tok.value!r} in field annotation block",
                        inner_tok.line,
                        inner_tok.column,
                    )
            self._expect(TokenType.RBRACE)
        return f

    # ------------------------------------------------------------------
    # Type references
    # ------------------------------------------------------------------

    def _parse_type_ref(self) -> TypeRef:
        """Parse a type reference.

        Handles primitive types, File, Directory, List<T>, Map<K,V>,
        Optional<T>, or a named type.
        """
        name_tok = self._expect(TokenType.IDENTIFIER)
        name = name_tok.value
        if name in _PRIMITIVE_TYPES:
            return PrimitiveTypeRef(primitive=_PRIMITIVE_TYPES[name])
        if name == "File":
            return FileTypeRef()
        if name == "Directory":
            return DirectoryTypeRef()
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
        """Parse: requires/provides <Name> [@version]"""
        self._expect(keyword)
        name_tok = self._expect(TokenType.IDENTIFIER)
        version: str | None = None
        if self._check(TokenType.AT):
            self._advance()
            ver_tok = self._expect(TokenType.IDENTIFIER)
            version = ver_tok.value
        return InterfaceRef(name=name_tok.value, version=version)

    # ------------------------------------------------------------------
    # Common attribute parsers
    # ------------------------------------------------------------------

    def _parse_string_attr(self, keyword: TokenType) -> str:
        """Parse: <keyword> = <string>"""
        self._expect(keyword)
        self._expect(TokenType.EQUALS)
        str_tok = self._expect(TokenType.STRING)
        return str_tok.value

    def _parse_tags(self) -> list[str]:
        """Parse: tags = [ "tag1", "tag2", ... ]"""
        self._expect(TokenType.TAGS)
        self._expect(TokenType.EQUALS)
        self._expect(TokenType.LBRACKET)
        tags: list[str] = []
        if not self._check(TokenType.RBRACKET):
            first = self._expect(TokenType.STRING)
            tags.append(first.value)
            while self._check(TokenType.COMMA):
                self._advance()
                tag = self._expect(TokenType.STRING)
                tags.append(tag.value)
        self._expect(TokenType.RBRACKET)
        return tags
