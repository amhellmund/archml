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
    """All token types produced by the ArchML scanner."""

    # Keywords
    SYSTEM = "system"
    COMPONENT = "component"
    USER = "user"
    INTERFACE = "interface"
    CONNECT = "connect"
    EXPOSE = "expose"
    TYPE = "type"
    ENUM = "enum"
    ARTIFACT = "artifact"
    REQUIRES = "requires"
    PROVIDES = "provides"
    AS = "as"
    FROM = "from"
    IMPORT = "import"
    USE = "use"
    EXTERNAL = "external"
    VARIANT = "variant"
    VARIANTS = "variants"
    # Symbols and operators
    LBRACE = "{"
    RBRACE = "}"
    LANGLE = "<"
    RANGLE = ">"
    COMMA = ","
    COLON = ":"
    AT = "@"
    SLASH = "/"
    ARROW = "->"
    DOLLAR = "$"
    DOT = "."

    # Literals
    TRIPLE_STRING = "TRIPLE_STRING"
    INTEGER = "INTEGER"

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


def tokenize(source: str, filename: str = "") -> list[Token]:
    """Tokenize ArchML source text into a sequence of tokens.

    Returns a list of tokens. The final token is always an EOF token.
    Comments and whitespace are consumed and not included in the output.

    Args:
        source: The full text of an .archml file.
        filename: Optional source file path included in error messages.

    Returns:
        A list of Token objects ending with a single EOF token.

    Raises:
        LexerError: On unexpected characters, unterminated string literals,
            or unterminated block comments.
    """
    return _Lexer(source, filename).tokenize()


# ################
# Implementation
# ################

_KEYWORDS: dict[str, TokenType] = {
    "system": TokenType.SYSTEM,
    "component": TokenType.COMPONENT,
    "user": TokenType.USER,
    "interface": TokenType.INTERFACE,
    "connect": TokenType.CONNECT,
    "expose": TokenType.EXPOSE,
    "type": TokenType.TYPE,
    "enum": TokenType.ENUM,
    "artifact": TokenType.ARTIFACT,
    "requires": TokenType.REQUIRES,
    "provides": TokenType.PROVIDES,
    "as": TokenType.AS,
    "from": TokenType.FROM,
    "import": TokenType.IMPORT,
    "use": TokenType.USE,
    "external": TokenType.EXTERNAL,
    "variant": TokenType.VARIANT,
    "variants": TokenType.VARIANTS,
}

_SINGLE_CHAR_TOKENS: dict[str, TokenType] = {
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    "<": TokenType.LANGLE,
    ">": TokenType.RANGLE,
    ",": TokenType.COMMA,
    ":": TokenType.COLON,
    "@": TokenType.AT,
    "/": TokenType.SLASH,
    "$": TokenType.DOLLAR,
    ".": TokenType.DOT,
}


class _Lexer:
    """Internal scanner state machine."""

    def __init__(self, source: str, filename: str = "") -> None:
        self._source = source
        self._filename = filename
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
            elif ch == "#":
                self._skip_line_comment()
            else:
                break

    def _skip_line_comment(self) -> None:
        """Consume from '#' through end-of-line (exclusive of the newline itself)."""
        while self._pos < len(self._source) and self._current() != "\n":
            self._advance()

    # ------------------------------------------------------------------
    # Token scanning dispatcher
    # ------------------------------------------------------------------

    def _scan_token(self) -> None:
        """Dispatch to the appropriate handler based on the current character."""
        ch = self._current()
        line = self._line
        col = self._column

        if ch == "-" and self._peek() == ">":
            self._advance()  # -
            self._advance()  # >
            self._tokens.append(Token(TokenType.ARROW, "->", line, col))
        elif ch in _SINGLE_CHAR_TOKENS:
            self._advance()
            self._tokens.append(Token(_SINGLE_CHAR_TOKENS[ch], ch, line, col))
        elif ch == '"':
            self._scan_string(line, col)
        elif ch.isdigit():
            self._scan_number(line, col)
        elif ch.isalpha() or ch == "_":
            self._scan_identifier_or_keyword(line, col)
        else:
            raise LexerError(f"Unexpected character: {ch!r}", line, col, self._filename)

    # ------------------------------------------------------------------
    # Literal scanners
    # ------------------------------------------------------------------

    def _scan_string(self, line: int, col: int) -> None:
        """Scan a triple-quoted string literal (\"\"\"...\"\"\").

        Only triple-quoted strings are supported. A lone or double quote
        raises a LexerError.
        """
        self._advance()  # first "
        if self._pos >= len(self._source) or self._current() != '"':
            raise LexerError('Expected triple-quoted string (""")', line, col, self._filename)
        self._advance()  # second "
        if self._pos >= len(self._source) or self._current() != '"':
            raise LexerError('Expected triple-quoted string (""")', line, col, self._filename)
        self._advance()  # third "
        self._scan_triple_quoted_string(line, col)

    def _scan_triple_quoted_string(self, line: int, col: int) -> None:
        """Scan a triple-quoted string (\"\"\"...\"\"\").

        Allows literal newlines. Supports the same escape sequences as
        single-quoted strings (\\n, \\t, \\\\, \\\").
        """
        chars: list[str] = []
        while self._pos < len(self._source):
            ch = self._current()
            # Check for closing """
            if (
                ch == '"'
                and self._pos + 2 < len(self._source)
                and self._source[self._pos + 1] == '"'
                and self._source[self._pos + 2] == '"'
            ):
                self._advance()  # first "
                self._advance()  # second "
                self._advance()  # third "
                self._tokens.append(Token(TokenType.TRIPLE_STRING, "".join(chars), line, col))
                return
            if ch == "\\":
                self._advance()
                if self._pos >= len(self._source):
                    raise LexerError("Unterminated triple-quoted string literal", line, col, self._filename)
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
                        self._filename,
                    )
                self._advance()
            else:
                chars.append(ch)
                self._advance()
        raise LexerError("Unterminated triple-quoted string literal", line, col, self._filename)

    def _scan_number(self, line: int, col: int) -> None:
        """Scan an integer."""
        start = self._pos
        while self._pos < len(self._source) and self._current().isdigit():
            self._advance()

        value = self._source[start : self._pos]
        self._tokens.append(Token(TokenType.INTEGER, value, line, col))

    def _scan_identifier_or_keyword(self, line: int, col: int) -> None:
        """Scan an identifier and map it to a keyword token type if applicable."""
        start = self._pos
        while self._pos < len(self._source) and (self._current().isalnum() or self._current() == "_"):
            self._advance()
        value = self._source[start : self._pos]
        token_type = _KEYWORDS.get(value, TokenType.IDENTIFIER)
        self._tokens.append(Token(token_type, value, line, col))
