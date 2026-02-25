# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Lexical scanner for .archml files.

Converts raw source text into a sequence of tokens for subsequent parsing.
"""

import enum
from dataclasses import dataclass

# ###############
# Public Interface
# ###############


class TokenType(enum.Enum):
    """All token types produced by the ArchML lexer."""

    # Keywords
    SYSTEM = "system"
    COMPONENT = "component"
    INTERFACE = "interface"
    TYPE = "type"
    ENUM = "enum"
    FIELD = "field"
    FILETYPE = "filetype"
    SCHEMA = "schema"
    REQUIRES = "requires"
    PROVIDES = "provides"
    CONNECT = "connect"
    ON = "on"
    FROM = "from"
    IMPORT = "import"
    USE = "use"
    EXTERNAL = "external"
    TAGS = "tags"
    TITLE = "title"
    DESCRIPTION = "description"
    TRUE = "true"
    FALSE = "false"

    # Symbols and operators
    LBRACE = "{"
    RBRACE = "}"
    LANGLE = "<"
    RANGLE = ">"
    LBRACKET = "["
    RBRACKET = "]"
    COMMA = ","
    DOT = "."
    COLON = ":"
    EQUALS = "="
    AT = "@"
    ARROW = "->"
    SLASH = "/"

    # Literals
    STRING = "STRING"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"

    # Identifiers
    IDENTIFIER = "IDENTIFIER"

    # End of file
    EOF = "EOF"


@dataclass(frozen=True)
class Token:
    """A lexical token with its source location.

    Attributes:
        type: The kind of token.
        value: The raw text of the token (or decoded string content for STRING tokens).
        line: 1-based line number where the token starts.
        column: 1-based column number where the token starts.
    """

    type: TokenType
    value: str
    line: int
    column: int


class LexerError(Exception):
    """Raised when the scanner encounters an invalid character or unterminated literal.

    Attributes:
        line: 1-based line number of the error.
        column: 1-based column number of the error.
    """

    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__(f"Line {line}, column {column}: {message}")
        self.line = line
        self.column = column


def tokenize(source: str) -> list[Token]:
    """Tokenize ArchML source text into a sequence of tokens.

    Returns a list of tokens. The final token is always an EOF token.
    Comments and whitespace are consumed and not included in the output.

    Args:
        source: The full text of an .archml file.

    Returns:
        A list of Token objects ending with a single EOF token.

    Raises:
        LexerError: On unexpected characters, unterminated string literals,
            or unterminated block comments.
    """
    return _Lexer(source).tokenize()


# ################
# Implementation
# ################

_KEYWORDS: dict[str, TokenType] = {
    "system": TokenType.SYSTEM,
    "component": TokenType.COMPONENT,
    "interface": TokenType.INTERFACE,
    "type": TokenType.TYPE,
    "enum": TokenType.ENUM,
    "field": TokenType.FIELD,
    "filetype": TokenType.FILETYPE,
    "schema": TokenType.SCHEMA,
    "requires": TokenType.REQUIRES,
    "provides": TokenType.PROVIDES,
    "connect": TokenType.CONNECT,
    "on": TokenType.ON,
    "from": TokenType.FROM,
    "import": TokenType.IMPORT,
    "use": TokenType.USE,
    "external": TokenType.EXTERNAL,
    "tags": TokenType.TAGS,
    "title": TokenType.TITLE,
    "description": TokenType.DESCRIPTION,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
}

_SINGLE_CHAR_TOKENS: dict[str, TokenType] = {
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    "<": TokenType.LANGLE,
    ">": TokenType.RANGLE,
    "[": TokenType.LBRACKET,
    "]": TokenType.RBRACKET,
    ",": TokenType.COMMA,
    ".": TokenType.DOT,
    ":": TokenType.COLON,
    "=": TokenType.EQUALS,
    "@": TokenType.AT,
    "/": TokenType.SLASH,
}


class _Lexer:
    """Internal scanner state machine."""

    def __init__(self, source: str) -> None:
        self._source = source
        self._pos = 0
        self._line = 1
        self._column = 1
        self._tokens: list[Token] = []

    def tokenize(self) -> list[Token]:
        """Run the scanner and return all tokens including the terminal EOF."""
        while self._pos < len(self._source):
            self._skip_whitespace_and_comments()
            if self._pos >= len(self._source):
                break
            self._scan_token()
        self._tokens.append(Token(TokenType.EOF, "", self._line, self._column))
        return self._tokens

    # ------------------------------------------------------------------
    # Low-level character access helpers
    # ------------------------------------------------------------------

    def _current(self) -> str:
        """Return the character at the current position, or '' at end of input."""
        if self._pos < len(self._source):
            return self._source[self._pos]
        return ""

    def _peek(self) -> str:
        """Return the character one position ahead, or '' at end of input."""
        if self._pos + 1 < len(self._source):
            return self._source[self._pos + 1]
        return ""

    def _advance(self) -> str:
        """Consume the current character, update position tracking, and return it."""
        ch = self._source[self._pos]
        self._pos += 1
        if ch == "\n":
            self._line += 1
            self._column = 1
        else:
            self._column += 1
        return ch

    # ------------------------------------------------------------------
    # Whitespace and comment skipping
    # ------------------------------------------------------------------

    def _skip_whitespace_and_comments(self) -> None:
        """Skip all whitespace and comment runs at the current position."""
        while self._pos < len(self._source):
            ch = self._current()
            if ch in " \t\r\n":
                self._advance()
            elif ch == "/" and self._peek() == "/":
                self._skip_line_comment()
            elif ch == "/" and self._peek() == "*":
                self._skip_block_comment()
            else:
                break

    def _skip_line_comment(self) -> None:
        """Consume from '//' through end-of-line (exclusive of the newline itself)."""
        while self._pos < len(self._source) and self._current() != "\n":
            self._advance()

    def _skip_block_comment(self) -> None:
        """Consume from '/*' through the matching '*/'."""
        start_line = self._line
        start_col = self._column
        self._advance()  # /
        self._advance()  # *
        while self._pos < len(self._source):
            if self._current() == "*" and self._peek() == "/":
                self._advance()  # *
                self._advance()  # /
                return
            self._advance()
        raise LexerError("Unterminated block comment", start_line, start_col)

    # ------------------------------------------------------------------
    # Token scanning dispatcher
    # ------------------------------------------------------------------

    def _scan_token(self) -> None:
        """Dispatch to the appropriate handler based on the current character."""
        ch = self._current()
        line = self._line
        col = self._column

        if ch in _SINGLE_CHAR_TOKENS:
            self._advance()
            self._tokens.append(Token(_SINGLE_CHAR_TOKENS[ch], ch, line, col))
        elif ch == "-":
            if self._peek() == ">":
                self._advance()  # -
                self._advance()  # >
                self._tokens.append(Token(TokenType.ARROW, "->", line, col))
            else:
                raise LexerError("Unexpected character: '-'", line, col)
        elif ch == '"':
            self._scan_string(line, col)
        elif ch.isdigit():
            self._scan_number(line, col)
        elif ch.isalpha() or ch == "_":
            self._scan_identifier_or_keyword(line, col)
        else:
            raise LexerError(f"Unexpected character: {ch!r}", line, col)

    # ------------------------------------------------------------------
    # Literal scanners
    # ------------------------------------------------------------------

    def _scan_string(self, line: int, col: int) -> None:
        """Scan a double-quoted string literal with escape sequences."""
        self._advance()  # opening "
        chars: list[str] = []
        while self._pos < len(self._source):
            ch = self._current()
            if ch == '"':
                self._advance()  # closing "
                self._tokens.append(Token(TokenType.STRING, "".join(chars), line, col))
                return
            if ch == "\n":
                raise LexerError("Unterminated string literal", line, col)
            if ch == "\\":
                self._advance()
                if self._pos >= len(self._source):
                    raise LexerError("Unterminated string literal", line, col)
                esc = self._current()
                if esc == "n":
                    chars.append("\n")
                elif esc == "t":
                    chars.append("\t")
                elif esc == "\\":
                    chars.append("\\")
                elif esc == '"':
                    chars.append('"')
                else:
                    raise LexerError(
                        f"Invalid escape sequence: '\\{esc}'",
                        self._line,
                        self._column,
                    )
                self._advance()
            else:
                chars.append(ch)
                self._advance()
        raise LexerError("Unterminated string literal", line, col)

    def _scan_number(self, line: int, col: int) -> None:
        """Scan an integer or floating-point literal.

        A float requires at least one digit on both sides of the decimal point.
        """
        start = self._pos
        while self._pos < len(self._source) and self._current().isdigit():
            self._advance()

        if (
            self._pos < len(self._source)
            and self._current() == "."
            and self._peek().isdigit()
        ):
            self._advance()  # consume the '.'
            while self._pos < len(self._source) and self._current().isdigit():
                self._advance()
            value = self._source[start : self._pos]
            self._tokens.append(Token(TokenType.FLOAT, value, line, col))
        else:
            value = self._source[start : self._pos]
            self._tokens.append(Token(TokenType.INTEGER, value, line, col))

    def _scan_identifier_or_keyword(self, line: int, col: int) -> None:
        """Scan an identifier and map it to a keyword token type if applicable."""
        start = self._pos
        while self._pos < len(self._source) and (
            self._current().isalnum() or self._current() == "_"
        ):
            self._advance()
        value = self._source[start : self._pos]
        token_type = _KEYWORDS.get(value, TokenType.IDENTIFIER)
        self._tokens.append(Token(token_type, value, line, col))
