# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ArchML lexical scanner."""

import pytest

from archml.compiler.scanner import LexerError, Token, TokenType, tokenize

# ###############
# Test Helpers
# ###############


def _tokens(source: str) -> list[Token]:
    """Return all tokens including the terminal EOF."""
    return tokenize(source)


def _tokens_no_eof(source: str) -> list[Token]:
    """Return all tokens except the terminal EOF token."""
    result = tokenize(source)
    assert result[-1].type == TokenType.EOF
    return result[:-1]


def _types(source: str) -> list[TokenType]:
    """Return the token types for all tokens except EOF."""
    return [tok.type for tok in _tokens_no_eof(source)]


def _values(source: str) -> list[str]:
    """Return the token values for all tokens except EOF."""
    return [tok.value for tok in _tokens_no_eof(source)]


# ###############
# EOF Handling
# ###############


class TestEof:
    def test_empty_string_produces_eof(self) -> None:
        tokens = _tokens("")
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF

    def test_eof_value_is_empty_string(self) -> None:
        tokens = _tokens("")
        assert len(tokens) == 1
        assert tokens[0].value == ""

    def test_eof_at_line_1_column_1_for_empty_input(self) -> None:
        tokens = _tokens("")
        assert len(tokens) == 1
        assert tokens[0].line == 1
        assert tokens[0].column == 1

    def test_whitespace_only_produces_eof(self) -> None:
        tokens = _tokens("   \t\n  ")
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF


# ###############
# Keywords
# ###############


class TestKeywords:
    @pytest.mark.parametrize(
        ("source", "expected_type"),
        [
            ("system", TokenType.SYSTEM),
            ("component", TokenType.COMPONENT),
            ("user", TokenType.USER),
            ("interface", TokenType.INTERFACE),
            ("type", TokenType.TYPE),
            ("enum", TokenType.ENUM),
            ("requires", TokenType.REQUIRES),
            ("provides", TokenType.PROVIDES),
            ("connect", TokenType.CONNECT),
            ("expose", TokenType.EXPOSE),
            ("as", TokenType.AS),
            ("from", TokenType.FROM),
            ("import", TokenType.IMPORT),
            ("use", TokenType.USE),
            ("external", TokenType.EXTERNAL),
            ("config", TokenType.CONFIG),
        ],
    )
    def test_keyword_recognized(self, source: str, expected_type: TokenType) -> None:
        tokens = _tokens_no_eof(source)
        assert len(tokens) == 1
        assert tokens[0].type == expected_type
        assert tokens[0].value == source

    def test_keywords_case_sensitive_uppercase_is_identifier(self) -> None:
        assert _types("System") == [TokenType.IDENTIFIER]
        assert _types("SYSTEM") == [TokenType.IDENTIFIER]
        assert _types("Component") == [TokenType.IDENTIFIER]

    def test_keyword_prefix_is_identifier(self) -> None:
        # 'sys' is not a keyword
        assert _types("sys") == [TokenType.IDENTIFIER]

    def test_keyword_with_suffix_is_identifier(self) -> None:
        # 'systems' is not a keyword
        assert _types("systems") == [TokenType.IDENTIFIER]

    def test_multiple_keywords_in_sequence(self) -> None:
        types = _types("system component interface")
        assert types == [TokenType.SYSTEM, TokenType.COMPONENT, TokenType.INTERFACE]


# ###############
# Identifiers
# ###############


class TestIdentifiers:
    @pytest.mark.parametrize(
        "source",
        [
            "order_service",
            "x",
            "_private",
            "service2",
            "OrderService",
            "PAYMENT",
            "a_b_c_d",
        ],
    )
    def test_identifier(self, source) -> None:
        tokens = _tokens_no_eof(source)
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == source

    def test_identifier_cannot_start_with_digit(self) -> None:
        # A digit starts a number token, so '2service' becomes INTEGER + IDENTIFIER
        types = _types("2service")
        assert types[0] == TokenType.INTEGER
        assert types[1] == TokenType.IDENTIFIER

    @pytest.mark.parametrize(
        "source",
        [
            "order-service",
            "a-b-c",
            "my-component-v2",
            "kebab-case-name",
        ],
    )
    def test_identifier_with_dashes(self, source: str) -> None:
        tokens = _tokens_no_eof(source)
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == source

    def test_identifier_cannot_start_with_dash(self) -> None:
        # A leading dash is not a valid identifier start — it is an unexpected char
        with pytest.raises(LexerError):
            tokenize("-leading")

    def test_arrow_after_identifier_not_consumed_as_dash(self) -> None:
        # 'a->b' must tokenize as IDENT ARROW IDENT, not as IDENT('-') RANGLE IDENT
        types = _types("a->b")
        assert types == [TokenType.IDENTIFIER, TokenType.ARROW, TokenType.IDENTIFIER]

    def test_dashed_ident_followed_by_arrow(self) -> None:
        # 'order-service -> result' must tokenize correctly
        tokens = _tokens_no_eof("order-service -> result")
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "order-service"
        assert tokens[1].type == TokenType.ARROW
        assert tokens[2].type == TokenType.IDENTIFIER
        assert tokens[2].value == "result"


# ###############
# Symbols and Operators
# ###############


class TestSymbols:
    @pytest.mark.parametrize(
        ("source", "expected_type"),
        [
            ("{", TokenType.LBRACE),
            ("}", TokenType.RBRACE),
            ("<", TokenType.LANGLE),
            (">", TokenType.RANGLE),
            (",", TokenType.COMMA),
            (":", TokenType.COLON),
            ("@", TokenType.AT),
            ("/", TokenType.SLASH),
        ],
    )
    def test_single_char_symbol(self, source: str, expected_type: TokenType) -> None:
        tokens = _tokens_no_eof(source)
        assert len(tokens) == 1
        assert tokens[0].type == expected_type
        assert tokens[0].value == source

    def test_dash_raises(self) -> None:
        with pytest.raises(LexerError):
            tokenize("-")

    def test_generic_type_angle_brackets(self) -> None:
        types = _types("List<T>")
        assert types == [
            TokenType.IDENTIFIER,
            TokenType.LANGLE,
            TokenType.IDENTIFIER,
            TokenType.RANGLE,
        ]

    def test_braces(self) -> None:
        types = _types("{}")
        assert types == [TokenType.LBRACE, TokenType.RBRACE]

    def test_equals_raises(self) -> None:
        with pytest.raises(LexerError):
            tokenize("=")

    def test_lbracket_raises(self) -> None:
        with pytest.raises(LexerError):
            tokenize("[")

    def test_rbracket_raises(self) -> None:
        with pytest.raises(LexerError):
            tokenize("]")

    def test_colon_in_field_declaration(self) -> None:
        types = _types("x: String")
        assert types == [
            TokenType.IDENTIFIER,
            TokenType.COLON,
            TokenType.IDENTIFIER,
        ]

    def test_at_symbol(self) -> None:
        types = _types("@v2")
        assert types == [TokenType.AT, TokenType.IDENTIFIER]

    def test_slash_in_import_path(self) -> None:
        types = _types("interfaces/order")
        assert types == [
            TokenType.IDENTIFIER,
            TokenType.SLASH,
            TokenType.IDENTIFIER,
        ]


# #####################
# Single-Quoted Strings
# #####################


class TestSingleQuotedStrings:
    def test_single_quote_raises(self) -> None:
        with pytest.raises(LexerError, match="Expected triple-quoted string"):
            tokenize('"hello"')

    def test_lone_quote_raises(self) -> None:
        with pytest.raises(LexerError, match="Expected triple-quoted string"):
            tokenize('"unterminated')

    def test_double_quote_raises(self) -> None:
        with pytest.raises(LexerError, match="Expected triple-quoted string"):
            tokenize('""')


# ###############
# Triple-Quoted String Literals
# ###############


class TestTripleQuotedStrings:
    def test_simple_triple_quoted_string(self) -> None:
        tokens = _tokens_no_eof('"""hello"""')
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.TRIPLE_STRING
        assert tokens[0].value == "hello"

    def test_empty_triple_quoted_string(self) -> None:
        tokens = _tokens_no_eof('""""""')
        assert tokens[0].type == TokenType.TRIPLE_STRING
        assert tokens[0].value == ""

    def test_triple_quoted_with_literal_newline(self) -> None:
        tokens = _tokens_no_eof('"""line1\nline2"""')
        assert tokens[0].type == TokenType.TRIPLE_STRING
        assert tokens[0].value == "line1\nline2"

    def test_triple_quoted_with_multiple_newlines(self) -> None:
        source = '"""\nfirst\nsecond\nthird\n"""'
        tokens = _tokens_no_eof(source)
        assert tokens[0].type == TokenType.TRIPLE_STRING
        assert tokens[0].value == "\nfirst\nsecond\nthird\n"

    def test_triple_quoted_with_single_double_quote_inside(self) -> None:
        tokens = _tokens_no_eof('"""say "hi" there"""')
        assert tokens[0].value == 'say "hi" there'

    def test_triple_quoted_with_two_double_quotes_inside(self) -> None:
        tokens = _tokens_no_eof('"""a ""b"""')
        assert tokens[0].value == 'a ""b'

    def test_triple_quoted_with_escape_newline(self) -> None:
        tokens = _tokens_no_eof(r'"""col1\ncol2"""')
        assert tokens[0].value == "col1\ncol2"

    def test_triple_quoted_with_escape_tab(self) -> None:
        tokens = _tokens_no_eof(r'"""a\tb"""')
        assert tokens[0].value == "a\tb"

    def test_triple_quoted_with_escape_backslash(self) -> None:
        tokens = _tokens_no_eof(r'"""back\\slash"""')
        assert tokens[0].value == "back\\slash"

    def test_triple_quoted_with_escape_quote(self) -> None:
        tokens = _tokens_no_eof(r'"""say \"hi\""""')
        assert tokens[0].value == 'say "hi"'

    def test_triple_quoted_produces_triple_string_token(self) -> None:
        tokens = _tokens_no_eof('"""content"""')
        assert tokens[0].type == TokenType.TRIPLE_STRING

    def test_triple_quoted_start_position_at_opening_quotes(self) -> None:
        tokens = _tokens_no_eof('   """hello"""')
        assert tokens[0].column == 4

    def test_triple_quoted_multiline_source_location(self) -> None:
        # Token line/col recorded at opening """
        source = '"""line1\nline2"""'
        tokens = _tokens_no_eof(source)
        assert tokens[0].line == 1
        assert tokens[0].column == 1

    def test_unterminated_triple_quoted_raises(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize('"""unterminated')
        assert "Unterminated triple-quoted string" in str(exc_info.value)

    def test_unterminated_triple_quoted_two_closing_raises(self) -> None:
        with pytest.raises(LexerError):
            tokenize('"""only two closing""')

    def test_triple_quoted_invalid_escape_raises(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize(r'"""bad\xescape"""')
        assert "Invalid escape sequence" in str(exc_info.value)

    def test_triple_quoted_followed_by_token(self) -> None:
        tokens = _tokens_no_eof('"""hello""" system')
        assert len(tokens) == 2
        assert tokens[0].type == TokenType.TRIPLE_STRING
        assert tokens[0].value == "hello"
        assert tokens[1].type == TokenType.SYSTEM

    def test_triple_quoted_as_docstring(self) -> None:
        source = '"""multi\nline"""'
        types = _types(source)
        assert types == [TokenType.TRIPLE_STRING]


# ###############
# Number Literals
# ###############


class TestNumberLiterals:
    def test_integer_zero(self) -> None:
        tokens = _tokens_no_eof("0")
        assert tokens[0].type == TokenType.INTEGER
        assert tokens[0].value == "0"

    def test_integer_single_digit(self) -> None:
        tokens = _tokens_no_eof("5")
        assert tokens[0].type == TokenType.INTEGER
        assert tokens[0].value == "5"

    def test_integer_multi_digit(self) -> None:
        tokens = _tokens_no_eof("42")
        assert tokens[0].type == TokenType.INTEGER
        assert tokens[0].value == "42"

    def test_integer_large(self) -> None:
        tokens = _tokens_no_eof("1000000")
        assert tokens[0].type == TokenType.INTEGER
        assert tokens[0].value == "1000000"

    def test_multiple_integers(self) -> None:
        tokens = _tokens_no_eof("1 2 3")
        assert len(tokens) == 3
        assert all(t.type == TokenType.INTEGER for t in tokens)

    def test_integer_followed_by_identifier(self) -> None:
        types = _types("42x")
        # '42x' -> INTEGER("42") + IDENTIFIER("x")
        assert types == [TokenType.INTEGER, TokenType.IDENTIFIER]


# ###############
# Comments
# ###############


class TestComments:
    def test_line_comment_skipped(self) -> None:
        tokens = _tokens_no_eof("# this is a comment")
        assert len(tokens) == 0

    def test_line_comment_does_not_consume_next_line(self) -> None:
        tokens = _tokens_no_eof("# comment\nsystem")
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.SYSTEM

    def test_line_comment_after_token(self) -> None:
        types = _types("system # the top-level system")
        assert types == [TokenType.SYSTEM]

    def test_line_comment_between_tokens(self) -> None:
        types = _types("system # comment\ncomponent")
        assert types == [TokenType.SYSTEM, TokenType.COMPONENT]

    def test_multiple_line_comments(self) -> None:
        source = "# first\n# second\nsystem"
        types = _types(source)
        assert types == [TokenType.SYSTEM]

    def test_hash_in_triple_string_not_comment(self) -> None:
        tokens = _tokens_no_eof('"""color: #ff0000"""')
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.TRIPLE_STRING
        assert tokens[0].value == "color: #ff0000"


# ###############
# Whitespace
# ###############


class TestWhitespace:
    def test_spaces_between_tokens(self) -> None:
        types = _types("system component")
        assert types == [TokenType.SYSTEM, TokenType.COMPONENT]

    def test_tabs_between_tokens(self) -> None:
        types = _types("system\tcomponent")
        assert types == [TokenType.SYSTEM, TokenType.COMPONENT]

    def test_newlines_between_tokens(self) -> None:
        types = _types("system\ncomponent")
        assert types == [TokenType.SYSTEM, TokenType.COMPONENT]

    def test_carriage_return_newline(self) -> None:
        types = _types("system\r\ncomponent")
        assert types == [TokenType.SYSTEM, TokenType.COMPONENT]

    def test_mixed_whitespace(self) -> None:
        types = _types("  system  \t\n  component  ")
        assert types == [TokenType.SYSTEM, TokenType.COMPONENT]

    def test_no_whitespace_between_symbols(self) -> None:
        types = _types("{}")
        assert types == [TokenType.LBRACE, TokenType.RBRACE]

    def test_leading_whitespace(self) -> None:
        types = _types("   system")
        assert types == [TokenType.SYSTEM]

    def test_trailing_whitespace(self) -> None:
        types = _types("system   ")
        assert types == [TokenType.SYSTEM]


# ###############
# Source Location Tracking
# ###############


class TestSourceLocations:
    def test_first_token_at_line1_col1(self) -> None:
        tokens = _tokens_no_eof("system")
        assert tokens[0].line == 1
        assert tokens[0].column == 1

    def test_second_token_column(self) -> None:
        tokens = _tokens_no_eof("system component")
        # "system" (6 chars) + 1 space = column 8 for "component"
        assert tokens[1].line == 1
        assert tokens[1].column == 8

    def test_token_on_second_line(self) -> None:
        tokens = _tokens_no_eof("system\ncomponent")
        assert tokens[1].line == 2
        assert tokens[1].column == 1

    def test_token_indented_on_second_line(self) -> None:
        tokens = _tokens_no_eof("system\n    component")
        assert tokens[1].line == 2
        assert tokens[1].column == 5

    def test_as_keyword_position(self) -> None:
        tokens = _tokens_no_eof("requires X as pay_in")
        as_tok = tokens[2]
        assert as_tok.type == TokenType.AS
        assert as_tok.line == 1
        assert as_tok.column == 12

    def test_triple_string_start_position_is_at_opening_quote(self) -> None:
        tokens = _tokens_no_eof('x: """hello"""')
        string_tok = tokens[2]
        assert string_tok.type == TokenType.TRIPLE_STRING
        assert string_tok.column == 4

    def test_eof_position_after_single_line(self) -> None:
        tokens = _tokens("abc")
        eof = tokens[-1]
        assert eof.line == 1
        assert eof.column == 4

    def test_eof_position_after_newline(self) -> None:
        tokens = _tokens("abc\n")
        eof = tokens[-1]
        assert eof.line == 2
        assert eof.column == 1


# ###############
# Error Handling
# ###############


class TestErrors:
    def test_unexpected_character_semicolon(self) -> None:
        with pytest.raises(LexerError):
            tokenize(";")

    def test_dollar_sign_produces_dollar_token(self) -> None:
        tokens = _tokens_no_eof("$payment")
        assert tokens[0].type == TokenType.DOLLAR
        assert tokens[0].value == "$"
        assert tokens[1].type == TokenType.IDENTIFIER
        assert tokens[1].value == "payment"

    def test_unexpected_character_tilde(self) -> None:
        with pytest.raises(LexerError):
            tokenize("~")

    def test_unexpected_character_question_mark(self) -> None:
        with pytest.raises(LexerError):
            tokenize("?")

    def test_error_includes_line_number(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize("\n\n~")
        assert exc_info.value.line == 3

    def test_error_includes_column_number(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize("   ~")
        assert exc_info.value.column == 4

    def test_error_message_format(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize("~")
        assert "1:1:" in str(exc_info.value)

    def test_error_message_format_with_filename(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize("~", filename="foo.farchml")
        assert "foo.farchml:1:1:" in str(exc_info.value)

    def test_unterminated_string_error_location(self) -> None:
        with pytest.raises(LexerError) as exc_info:
            tokenize('   "unterminated')
        error = exc_info.value
        assert error.line == 1
        assert error.column == 4


# ###############
# Structural Patterns
# ###############


class TestStructuralPatterns:
    """Tests for common ArchML structural patterns from the language spec."""

    def test_simple_component_declaration(self) -> None:
        source = "component OrderService {}"
        types = _types(source)
        assert types == [
            TokenType.COMPONENT,
            TokenType.IDENTIFIER,
            TokenType.LBRACE,
            TokenType.RBRACE,
        ]

    def test_interface_with_version(self) -> None:
        source = "interface OrderRequest @v2 {}"
        types = _types(source)
        assert types == [
            TokenType.INTERFACE,
            TokenType.IDENTIFIER,
            TokenType.AT,
            TokenType.IDENTIFIER,
            TokenType.LBRACE,
            TokenType.RBRACE,
        ]

    def test_field_declaration_with_type(self) -> None:
        source = "order_id: String"
        types = _types(source)
        assert types == [
            TokenType.IDENTIFIER,
            TokenType.COLON,
            TokenType.IDENTIFIER,
        ]

    def test_field_with_container_type(self) -> None:
        source = "items: List<OrderItem>"
        types = _types(source)
        assert types == [
            TokenType.IDENTIFIER,
            TokenType.COLON,
            TokenType.IDENTIFIER,
            TokenType.LANGLE,
            TokenType.IDENTIFIER,
            TokenType.RANGLE,
        ]

    def test_map_type(self) -> None:
        source = "Map<K, V>"
        types = _types(source)
        assert types == [
            TokenType.IDENTIFIER,
            TokenType.LANGLE,
            TokenType.IDENTIFIER,
            TokenType.COMMA,
            TokenType.IDENTIFIER,
            TokenType.RANGLE,
        ]

    def test_optional_type(self) -> None:
        source = "Optional<String>"
        types = _types(source)
        assert types == [
            TokenType.IDENTIFIER,
            TokenType.LANGLE,
            TokenType.IDENTIFIER,
            TokenType.RANGLE,
        ]

    def test_connect_statement(self) -> None:
        source = "connect A.PaymentRequest -> $payment -> B.PaymentRequest"
        types = _types(source)
        assert types == [
            TokenType.CONNECT,
            TokenType.IDENTIFIER,
            TokenType.DOT,
            TokenType.IDENTIFIER,
            TokenType.ARROW,
            TokenType.DOLLAR,
            TokenType.IDENTIFIER,
            TokenType.ARROW,
            TokenType.IDENTIFIER,
            TokenType.DOT,
            TokenType.IDENTIFIER,
        ]

    def test_expose_statement(self) -> None:
        source = "expose Processor.OrderConfirmation as confirmed"
        types = _types(source)
        assert types == [
            TokenType.EXPOSE,
            TokenType.IDENTIFIER,
            TokenType.DOT,
            TokenType.IDENTIFIER,
            TokenType.AS,
            TokenType.IDENTIFIER,
        ]

    def test_requires_as_declaration(self) -> None:
        source = "requires PaymentRequest as pay_in"
        types = _types(source)
        assert types == [
            TokenType.REQUIRES,
            TokenType.IDENTIFIER,
            TokenType.AS,
            TokenType.IDENTIFIER,
        ]

    def test_arrow_token(self) -> None:
        tokens = _tokens_no_eof("->")
        assert tokens[0].type == TokenType.ARROW
        assert tokens[0].value == "->"

    def test_import_statement(self) -> None:
        source = "from interfaces/order import OrderRequest, OrderConfirmation"
        types = _types(source)
        assert types == [
            TokenType.FROM,
            TokenType.IDENTIFIER,
            TokenType.SLASH,
            TokenType.IDENTIFIER,
            TokenType.IMPORT,
            TokenType.IDENTIFIER,
            TokenType.COMMA,
            TokenType.IDENTIFIER,
        ]

    def test_use_statement(self) -> None:
        source = "use component OrderService"
        types = _types(source)
        assert types == [
            TokenType.USE,
            TokenType.COMPONENT,
            TokenType.IDENTIFIER,
        ]

    def test_external_system_declaration(self) -> None:
        source = "external system StripeAPI {}"
        types = _types(source)
        assert types == [
            TokenType.EXTERNAL,
            TokenType.SYSTEM,
            TokenType.IDENTIFIER,
            TokenType.LBRACE,
            TokenType.RBRACE,
        ]

    def test_inline_variant_annotation_syntax(self) -> None:
        source = "component<cloud, on_premise>"
        types = _types(source)
        assert types == [
            TokenType.COMPONENT,
            TokenType.LANGLE,
            TokenType.IDENTIFIER,
            TokenType.COMMA,
            TokenType.IDENTIFIER,
            TokenType.RANGLE,
        ]

    def test_docstring_description(self) -> None:
        source = '"""Accepts and validates customer orders."""'
        types = _types(source)
        assert types == [TokenType.TRIPLE_STRING]

    def test_requires_declaration(self) -> None:
        source = "requires OrderRequest"
        types = _types(source)
        assert types == [TokenType.REQUIRES, TokenType.IDENTIFIER]

    def test_provides_declaration(self) -> None:
        source = "provides OrderConfirmation"
        types = _types(source)
        assert types == [TokenType.PROVIDES, TokenType.IDENTIFIER]

    def test_true_is_identifier(self) -> None:
        source = "true"
        types = _types(source)
        assert types == [TokenType.IDENTIFIER]

    def test_false_is_identifier(self) -> None:
        source = "false"
        types = _types(source)
        assert types == [TokenType.IDENTIFIER]

    def test_connect_with_inline_variant(self) -> None:
        source = "connect<cloud> A.PaymentRequest -> $payment -> B.PaymentRequest"
        types = _types(source)
        assert types == [
            TokenType.CONNECT,
            TokenType.LANGLE,
            TokenType.IDENTIFIER,
            TokenType.RANGLE,
            TokenType.IDENTIFIER,
            TokenType.DOT,
            TokenType.IDENTIFIER,
            TokenType.ARROW,
            TokenType.DOLLAR,
            TokenType.IDENTIFIER,
            TokenType.ARROW,
            TokenType.IDENTIFIER,
            TokenType.DOT,
            TokenType.IDENTIFIER,
        ]

    def test_cross_repo_import(self) -> None:
        source = "from @payments/services/payment import PaymentService"
        types = _types(source)
        assert types == [
            TokenType.FROM,
            TokenType.AT,
            TokenType.IDENTIFIER,
            TokenType.SLASH,
            TokenType.IDENTIFIER,
            TokenType.SLASH,
            TokenType.IDENTIFIER,
            TokenType.IMPORT,
            TokenType.IDENTIFIER,
        ]

    def test_enum_declaration(self) -> None:
        source = """
            enum OrderStatus {
                Pending
                Confirmed
            }
        """
        types = _types(source)
        assert types == [
            TokenType.ENUM,
            TokenType.IDENTIFIER,
            TokenType.LBRACE,
            TokenType.IDENTIFIER,
            TokenType.IDENTIFIER,
            TokenType.RBRACE,
        ]

    def test_type_declaration(self) -> None:
        source = """
            type OrderItem {
                product_id: String
                quantity: Int
            }
        """
        types = _types(source)
        assert types == [
            TokenType.TYPE,
            TokenType.IDENTIFIER,
            TokenType.LBRACE,
            TokenType.IDENTIFIER,
            TokenType.COLON,
            TokenType.IDENTIFIER,
            TokenType.IDENTIFIER,
            TokenType.COLON,
            TokenType.IDENTIFIER,
            TokenType.RBRACE,
        ]


# ###############
# Full Example Snippet
# ###############


class TestFullExample:
    """Validate a real-world multi-construct ArchML snippet end-to-end."""

    def test_interface_block(self) -> None:
        source = '''
            # Interface definition
            interface OrderRequest {
                """Payload for submitting a new customer order."""

                order_id: String
                items: List<OrderItem>
                total_amount: Float
            }
        '''
        tokens = _tokens_no_eof(source)
        # First real token should be INTERFACE (comment skipped)
        assert tokens[0].type == TokenType.INTERFACE
        assert tokens[1].type == TokenType.IDENTIFIER
        assert tokens[1].value == "OrderRequest"
        # Verify the TRIPLE_STRING values
        triple_values = [t.value for t in tokens if t.type == TokenType.TRIPLE_STRING]
        assert "Payload for submitting a new customer order." in triple_values

    def test_system_with_connect(self) -> None:
        source = """
            system ECommerce {
                component PaymentGateway {
                    provides PaymentRequest
                }

                component OrderService {
                    requires PaymentRequest
                }

                connect PaymentGateway.PaymentRequest -> $payment -> OrderService.PaymentRequest
            }
        """
        tokens = _tokens_no_eof(source)
        assert tokens[0].type == TokenType.SYSTEM
        connect_tokens = [t for t in tokens if t.type == TokenType.CONNECT]
        arrow_tokens = [t for t in tokens if t.type == TokenType.ARROW]
        dollar_tokens = [t for t in tokens if t.type == TokenType.DOLLAR]
        assert len(connect_tokens) == 1
        assert len(arrow_tokens) == 2
        assert len(dollar_tokens) == 1

    def test_integer_values_in_source(self) -> None:
        source = "quantity: Int"
        tokens = _tokens_no_eof(source)
        # 'Int' is an identifier, not a number
        assert tokens[2].type == TokenType.IDENTIFIER
        assert tokens[2].value == "Int"


# ###############
# Variant Keywords
# ###############


class TestVariantAndAttributeSyntax:
    """Tests for inline <variant> annotation and @attribute syntax tokens."""

    def test_variant_is_plain_identifier(self) -> None:
        # 'variant' is no longer a keyword — it scans as IDENTIFIER
        assert _types("variant") == [TokenType.IDENTIFIER]

    def test_variants_is_plain_identifier(self) -> None:
        # 'variants' is no longer a keyword — it scans as IDENTIFIER
        assert _types("variants") == [TokenType.IDENTIFIER]

    def test_system_with_single_variant(self) -> None:
        types = _types("system<cloud>")
        assert types == [TokenType.SYSTEM, TokenType.LANGLE, TokenType.IDENTIFIER, TokenType.RANGLE]

    def test_component_with_multiple_variants(self) -> None:
        types = _types("component<cloud, on_premise>")
        assert types == [
            TokenType.COMPONENT,
            TokenType.LANGLE,
            TokenType.IDENTIFIER,
            TokenType.COMMA,
            TokenType.IDENTIFIER,
            TokenType.RANGLE,
        ]

    def test_requires_with_variant(self) -> None:
        types = _types("requires<cloud> PaymentRequest")
        assert types == [
            TokenType.REQUIRES,
            TokenType.LANGLE,
            TokenType.IDENTIFIER,
            TokenType.RANGLE,
            TokenType.IDENTIFIER,
        ]

    def test_custom_attribute_single_value(self) -> None:
        types = _types("@team: platform")
        assert types == [
            TokenType.AT,
            TokenType.IDENTIFIER,
            TokenType.COLON,
            TokenType.IDENTIFIER,
        ]

    def test_custom_attribute_multiple_values(self) -> None:
        types = _types("@tags: critical, payments")
        assert types == [
            TokenType.AT,
            TokenType.IDENTIFIER,
            TokenType.COLON,
            TokenType.IDENTIFIER,
            TokenType.COMMA,
            TokenType.IDENTIFIER,
        ]
