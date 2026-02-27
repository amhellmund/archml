# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for the ArchML compiler pipeline.

These tests exercise the full compiler pipeline — scanning, parsing, and
semantic analysis — against real .archml files stored in tests/data/. They
serve as both regression tests and living documentation of which constructs
the compiler accepts or rejects.
"""

from __future__ import annotations

from pathlib import Path

from archml.compiler.parser import parse
from archml.compiler.semantic_analysis import SemanticError, analyze
from archml.model.entities import ArchFile

# ###############
# Helpers
# ###############

DATA_DIR = Path(__file__).parent.parent / "data"
POSITIVE_DIR = DATA_DIR / "positive"
NEGATIVE_DIR = DATA_DIR / "negative"


def _compile(path: Path, resolved_imports: dict[str, ArchFile] | None = None) -> list[SemanticError]:
    """Parse and semantically analyse the given .archml file."""
    source = path.read_text(encoding="utf-8")
    arch_file = parse(source)
    return analyze(arch_file, resolved_imports=resolved_imports)


def _messages(errors: list[SemanticError]) -> list[str]:
    return [e.message for e in errors]


def _assert_clean(path: Path, resolved_imports: dict[str, ArchFile] | None = None) -> None:
    errors = _compile(path, resolved_imports)
    assert errors == [], f"{path.name}: expected no errors but got:\n" + "\n".join(f"  - {e.message}" for e in errors)


def _assert_errors(path: Path, *fragments: str, resolved_imports: dict[str, ArchFile] | None = None) -> None:
    """Assert that at least one error matching each fragment is present."""
    errors = _compile(path, resolved_imports)
    messages = _messages(errors)
    assert messages, f"{path.name}: expected errors but got none"
    for fragment in fragments:
        assert any(fragment in m for m in messages), (
            f"{path.name}: expected an error containing {fragment!r}, but got: {messages}"
        )


# ###############
# Positive Examples
# ###############


class TestPositiveExamples:
    """All files in tests/data/positive/ should compile without errors."""

    def test_minimal_component(self) -> None:
        _assert_clean(POSITIVE_DIR / "minimal_component.archml")

    def test_types_and_enums(self) -> None:
        _assert_clean(POSITIVE_DIR / "types_and_enums.archml")

    def test_interfaces(self) -> None:
        _assert_clean(POSITIVE_DIR / "interfaces.archml")

    def test_nested_components(self) -> None:
        _assert_clean(POSITIVE_DIR / "nested_components.archml")

    def test_system_with_connections(self) -> None:
        _assert_clean(POSITIVE_DIR / "system_with_connections.archml")

    def test_versioned_interfaces(self) -> None:
        _assert_clean(POSITIVE_DIR / "versioned_interfaces.archml")

    def test_imports_types_source(self) -> None:
        """The types source file itself should be self-consistent."""
        _assert_clean(POSITIVE_DIR / "imports" / "types.archml")

    def test_imports_order_service_without_resolver(self) -> None:
        """Without a resolver, imported names are accepted without cross-file check."""
        _assert_clean(POSITIVE_DIR / "imports" / "order_service.archml")

    def test_imports_order_service_with_resolver(self) -> None:
        """With a resolver, the imported entities are verified against the source."""
        types_path = POSITIVE_DIR / "imports" / "types.archml"
        types_source = parse(types_path.read_text(encoding="utf-8"))
        resolved = {"imports/types": types_source}
        _assert_clean(POSITIVE_DIR / "imports" / "order_service.archml", resolved)

    def test_imports_ecommerce_system_with_resolver(self) -> None:
        """Full multi-file scenario: system imports from types and order_service."""
        types_path = POSITIVE_DIR / "imports" / "types.archml"
        order_path = POSITIVE_DIR / "imports" / "order_service.archml"
        types_source = parse(types_path.read_text(encoding="utf-8"))
        order_source = parse(order_path.read_text(encoding="utf-8"))
        resolved = {
            "imports/types": types_source,
            "imports/order_service": order_source,
        }
        _assert_clean(POSITIVE_DIR / "imports" / "ecommerce_system.archml", resolved)


# ###############
# Negative Examples
# ###############


class TestNegativeExamples:
    """All files in tests/data/negative/ should produce at least one semantic error."""

    def test_duplicate_enum_name(self) -> None:
        _assert_errors(
            NEGATIVE_DIR / "duplicate_enum_name.archml",
            "Duplicate enum name 'OrderStatus'",
        )

    def test_duplicate_type_name(self) -> None:
        _assert_errors(
            NEGATIVE_DIR / "duplicate_type_name.archml",
            "Duplicate type name 'Address'",
        )

    def test_duplicate_interface(self) -> None:
        path = NEGATIVE_DIR / "duplicate_interface.archml"
        _assert_errors(
            path,
            "Duplicate interface definition 'OrderRequest'",
            "Duplicate interface definition 'OrderRequest@v2'",
        )

    def test_duplicate_component_name(self) -> None:
        path = NEGATIVE_DIR / "duplicate_component_name.archml"
        _assert_errors(
            path,
            "Duplicate component name 'OrderService'",
            "Duplicate component name 'Worker'",
        )

    def test_duplicate_enum_values(self) -> None:
        path = NEGATIVE_DIR / "duplicate_enum_values.archml"
        _assert_errors(
            path,
            "Duplicate value 'Active' in enum 'Status'",
            "Duplicate value 'Red' in enum 'Color'",
        )

    def test_duplicate_field_names(self) -> None:
        path = NEGATIVE_DIR / "duplicate_field_names.archml"
        _assert_errors(
            path,
            "Duplicate field name 'street' in type 'Address'",
            "Duplicate field name 'order_id' in interface 'OrderRequest'",
        )

    def test_undefined_type_ref(self) -> None:
        path = NEGATIVE_DIR / "undefined_type_ref.archml"
        _assert_errors(
            path,
            "Undefined type 'OrderStatus'",
            "Undefined type 'OrderItem'",
            "Undefined type 'UnknownMeta'",
            "Undefined type 'BadKey'",
        )

    def test_undefined_interface_ref(self) -> None:
        path = NEGATIVE_DIR / "undefined_interface_ref.archml"
        _assert_errors(
            path,
            "refers to unknown interface 'OrderRequest'",
            "refers to unknown interface 'PaymentResult'",
            "refers to unknown interface 'ExternalFeed'",
        )

    def test_undefined_connection_endpoint(self) -> None:
        path = NEGATIVE_DIR / "undefined_connection_endpoint.archml"
        _assert_errors(
            path,
            "connection source 'GhostProducer' is not a known member entity",
            "connection target 'GhostOutput' is not a known member entity",
        )

    def test_wrong_interface_version(self) -> None:
        path = NEGATIVE_DIR / "wrong_interface_version.archml"
        _assert_errors(
            path,
            "no version 'v1' of interface 'OrderRequest' is defined",
            "no version 'old' of interface 'PaymentRequest' is defined",
        )

    def test_component_system_name_conflict(self) -> None:
        path = NEGATIVE_DIR / "component_system_name_conflict.archml"
        _assert_errors(
            path,
            "name 'Services' is used for both a component and a sub-system",
        )

    def test_enum_type_name_conflict(self) -> None:
        path = NEGATIVE_DIR / "enum_type_name_conflict.archml"
        _assert_errors(
            path,
            "Name 'Status' is defined as both an enum and a type",
        )

    def test_import_undefined_entity_without_resolver(self) -> None:
        """Without resolver, no import errors — validation skipped."""
        path = NEGATIVE_DIR / "imports" / "consumer.archml"
        errors = _compile(path)
        # Without resolver, no import errors should be raised
        import_errors = [e for e in errors if "is not defined in" in e.message or "could not be resolved" in e.message]
        assert import_errors == [], f"Expected no import errors without resolver, but got: {import_errors}"

    def test_import_undefined_entity_with_resolver(self) -> None:
        """With resolver, missing entities are reported."""
        consumer_path = NEGATIVE_DIR / "imports" / "consumer.archml"
        source_path = NEGATIVE_DIR / "imports" / "source.archml"
        source_file = parse(source_path.read_text(encoding="utf-8"))
        resolved = {"imports/source": source_file}
        _assert_errors(
            consumer_path,
            "'OrderConfirmation' is not defined in 'imports/source'",
            "'MissingEnum' is not defined in 'imports/source'",
            resolved_imports=resolved,
        )

    def test_import_missing_source_file_with_resolver(self) -> None:
        """Source path not present in resolver map is reported as unresolvable."""
        consumer_path = NEGATIVE_DIR / "imports" / "consumer.archml"
        # Provide an empty resolver — source.archml not included
        _assert_errors(
            consumer_path,
            "'imports/source' could not be resolved",
            resolved_imports={},
        )


# ###############
# Comprehensive Pipeline Tests
# ###############


class TestPipelineComprehensive:
    """End-to-end tests covering complex multi-construct scenarios."""

    def test_large_types_file_parses_and_passes(self) -> None:
        """The full types+enums+interfaces example should be error-free."""
        source = """
enum OrderStatus {
    Pending
    Confirmed
    Shipped
    Delivered
    Cancelled
}

enum PaymentMethod {
    CreditCard
    BankTransfer
}

type OrderItem {
    field product_id: String
    field quantity: Int
    field unit_price: Decimal
}

interface OrderRequest {
    field order_id: String
    field customer_id: String
    field items: List<OrderItem>
}

interface OrderRequest @v2 {
    field order_id: String
    field customer_id: String
    field items: List<OrderItem>
    field payment_method: PaymentMethod
}

interface OrderConfirmation {
    field order_id: String
    field status: OrderStatus
    field confirmed_at: Timestamp
}

interface PaymentRequest {
    field order_id: String
    field amount: Decimal
    field currency: String
}

interface PaymentResult {
    field order_id: String
    field success: Bool
    field transaction_id: Optional<String>
}

component OrderService {
    requires OrderRequest @v2
    requires PaymentRequest
    provides OrderConfirmation
}

component PaymentGateway {
    requires PaymentRequest
    provides PaymentResult
}

external system StripeAPI {
    requires PaymentRequest
    provides PaymentResult
}

system ECommerce {
    component OrderServiceInst {
        requires OrderRequest @v2
        requires PaymentRequest
        provides OrderConfirmation
    }
    component PaymentGatewayInst {
        requires PaymentRequest
        provides PaymentResult
    }
    connect OrderServiceInst -> PaymentGatewayInst by PaymentRequest
}
"""
        arch_file = parse(source)
        errors = analyze(arch_file)
        assert errors == [], f"Expected clean but got: {[e.message for e in errors]}"

    def test_multiple_errors_in_one_file(self) -> None:
        """A file with many problems should report all of them, not just the first."""
        source = """
enum Dup { A }
enum Dup { B }

type Bad { field x: UnknownType }

component C1 {
    requires MissingInterface
}

system S1 {
    component Worker {}
    component Worker {}
}
"""
        arch_file = parse(source)
        errors = analyze(arch_file)
        messages = [e.message for e in errors]
        assert any("Duplicate enum name 'Dup'" in m for m in messages)
        assert any("Undefined type 'UnknownType'" in m for m in messages)
        assert any("refers to unknown interface 'MissingInterface'" in m for m in messages)
        assert any("Duplicate component name 'Worker'" in m for m in messages)

    def test_deeply_nested_system_structure(self) -> None:
        """Nested systems and components should all be checked recursively."""
        source = """
interface Signal { field v: Int }

system Outer {
    system Middle {
        component Inner {
            provides Signal
        }
        component Sink {
            requires Signal
        }
        connect Inner -> Sink by Signal
    }
}
"""
        arch_file = parse(source)
        errors = analyze(arch_file)
        assert errors == [], f"Expected clean but got: {[e.message for e in errors]}"

    def test_deeply_nested_with_error(self) -> None:
        """An error deep in a nested structure should still be reported."""
        source = """
interface Signal { field v: Int }

system Outer {
    system Middle {
        component Inner {
            provides Signal
        }
        connect Inner -> UnknownTarget by Signal
    }
}
"""
        arch_file = parse(source)
        errors = analyze(arch_file)
        assert any("'UnknownTarget' is not a known member entity" in e.message for e in errors)

    def test_file_and_directory_type_refs_are_valid(self) -> None:
        """File and Directory types require no resolution and are always valid."""
        source = """
interface Artifacts {
    field report: File {
        filetype = "PDF"
        schema = "Monthly report."
    }
    field exports: Directory {
        schema = "Contains CSV files."
    }
}
"""
        arch_file = parse(source)
        errors = analyze(arch_file)
        assert errors == [], f"Expected clean but got: {[e.message for e in errors]}"

    def test_use_statement_adds_component_to_scope(self) -> None:
        """Components added via 'use' are valid connection endpoints."""
        source = """
from services import OrderService

interface PaymentRequest { field amount: Decimal }

system ECommerce {
    use component OrderService
    component PaymentGateway {
        requires PaymentRequest
    }
    connect OrderService -> PaymentGateway by PaymentRequest
}
"""
        arch_file = parse(source)
        errors = analyze(arch_file)
        # OrderService is in the imported names list, and 'use component' adds it
        # as a stub component in the system — the connection should be valid.
        conn_errors = [e for e in errors if "is not a known member entity" in e.message]
        assert conn_errors == [], f"Connection endpoint errors: {conn_errors}"
