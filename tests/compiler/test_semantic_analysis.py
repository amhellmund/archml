# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the ArchML semantic analysis module."""

from archml.compiler.parser import parse
from archml.compiler.semantic_analysis import SemanticError, analyze
from archml.model.entities import (
    ArchFile,
    Component,
    ConnectDef,
    EnumDef,
    InterfaceDef,
    InterfaceRef,
    System,
)
from archml.model.types import FieldDef, ListTypeRef, NamedTypeRef

# ###############
# Test Helpers
# ###############


def _analyze(source: str, resolved_imports: dict[str, ArchFile] | None = None) -> list[SemanticError]:
    """Parse source and run semantic analysis."""
    arch_file = parse(source)
    return analyze(arch_file, resolved_imports=resolved_imports)


def _messages(errors: list[SemanticError]) -> list[str]:
    """Extract error messages from a list of SemanticError instances."""
    return [e.message for e in errors]


def _assert_clean(source: str, resolved_imports: dict[str, ArchFile] | None = None) -> None:
    """Assert that a source string produces no semantic errors."""
    errors = _analyze(source, resolved_imports)
    assert errors == [], f"Expected no errors but got: {[e.message for e in errors]}"


def _assert_error(
    source: str,
    expected_fragment: str,
    resolved_imports: dict[str, ArchFile] | None = None,
) -> None:
    """Assert that exactly one semantic error containing expected_fragment is produced."""
    errors = _analyze(source, resolved_imports)
    messages = _messages(errors)
    assert any(expected_fragment in m for m in messages), (
        f"Expected error containing {expected_fragment!r} but got: {messages}"
    )


# ###############
# Clean Files
# ###############


class TestCleanFile:
    def test_empty_file_has_no_errors(self) -> None:
        _assert_clean("")

    def test_single_component_no_ports(self) -> None:
        _assert_clean("""
component Foo {
    title = "Foo"
}
""")

    def test_interface_with_primitive_fields(self) -> None:
        _assert_clean("""
interface OrderRequest {
    field order_id: String
    field amount: Decimal
    field count: Int
}
""")

    def test_component_with_known_interface(self) -> None:
        _assert_clean("""
interface OrderRequest {
    field order_id: String
}

component OrderService {
    requires OrderRequest
}
""")

    def test_type_with_known_enum_field(self) -> None:
        _assert_clean("""
enum Color {
    Red
    Green
    Blue
}

type Pixel {
    field color: Color
    field brightness: Int
}
""")

    def test_interface_with_known_type_field(self) -> None:
        _assert_clean("""
type Address {
    field street: String
    field city: String
}

interface Delivery {
    field address: Address
}
""")

    def test_system_with_components_and_connect(self) -> None:
        _assert_clean("""
interface DataFeed {
    field payload: String
}

system Pipeline {
    component Producer {
        provides DataFeed
    }

    component Consumer {
        requires DataFeed
    }

    connect Producer.DataFeed -> $feed -> Consumer.DataFeed
}
""")

    def test_nested_components_with_connect(self) -> None:
        _assert_clean("""
interface Signal {
    field value: Bool
}

component Router {
    component Input {
        provides Signal
    }

    component Output {
        requires Signal
    }

    connect Input.Signal -> $sig -> Output.Signal
}
""")

    def test_external_system(self) -> None:
        _assert_clean("""
interface PaymentRequest {
    field amount: Decimal
}

external system StripeAPI {
    requires PaymentRequest
}
""")

    def test_versioned_interface_matching_ref(self) -> None:
        _assert_clean("""
interface OrderRequest @v2 {
    field order_id: String
    field version: Int
}

component OrderService {
    requires OrderRequest @v2
}
""")

    def test_multiple_interface_versions(self) -> None:
        _assert_clean("""
interface OrderRequest {
    field order_id: String
}

interface OrderRequest @v2 {
    field order_id: String
    field version: Int
}

component ServiceA {
    requires OrderRequest
}

component ServiceB {
    requires OrderRequest @v2
}
""")

    def test_list_type_ref_with_known_type(self) -> None:
        _assert_clean("""
type Item {
    field name: String
}

interface Basket {
    field items: List<Item>
}
""")

    def test_map_type_ref_with_known_types(self) -> None:
        _assert_clean("""
enum Language {
    English
    French
}

type Translation {
    field text: String
}

interface Catalog {
    field entries: Map<Language, Translation>
}
""")

    def test_optional_type_ref_with_known_type(self) -> None:
        _assert_clean("""
type Meta {
    field key: String
}

interface Response {
    field meta: Optional<Meta>
}
""")

    def test_interface_used_as_type_ref_in_field(self) -> None:
        _assert_clean("""
interface Config {
    field host: String
    field port: Int
}

type ServiceSpec {
    field config: Config
}
""")


# ###############
# Duplicate Top-Level Names
# ###############


class TestDuplicateTopLevelNames:
    def test_duplicate_enum_name(self) -> None:
        _assert_error(
            """
enum Status {
    Active
}
enum Status {
    Inactive
}
""",
            "Duplicate enum name 'Status'",
        )

    def test_duplicate_type_name(self) -> None:
        _assert_error(
            """
type Address { field street: String }
type Address { field city: String }
""",
            "Duplicate type name 'Address'",
        )

    def test_duplicate_component_name(self) -> None:
        _assert_error(
            """
component OrderService {}
component OrderService {}
""",
            "Duplicate component name 'OrderService'",
        )

    def test_duplicate_system_name(self) -> None:
        _assert_error(
            """
system ECommerce {}
system ECommerce {}
""",
            "Duplicate system name 'ECommerce'",
        )

    def test_duplicate_interface_same_name_no_version(self) -> None:
        _assert_error(
            """
interface OrderRequest { field a: String }
interface OrderRequest { field b: Int }
""",
            "Duplicate interface definition 'OrderRequest'",
        )

    def test_duplicate_interface_same_name_same_version(self) -> None:
        _assert_error(
            """
interface OrderRequest @v2 { field a: String }
interface OrderRequest @v2 { field b: Int }
""",
            "Duplicate interface definition 'OrderRequest@v2'",
        )

    def test_different_interface_versions_are_ok(self) -> None:
        _assert_clean("""
interface OrderRequest { field a: String }
interface OrderRequest @v2 { field b: Int }
""")

    def test_enum_and_type_same_name_conflict(self) -> None:
        _assert_error(
            """
enum Foo {
    Bar
}
type Foo { field x: String }
""",
            "Name 'Foo' is defined as both an enum and a type",
        )

    def test_third_occurrence_of_duplicate_name(self) -> None:
        errors = _analyze("""
enum Status {
    Active
}
enum Status {
    Inactive
}
enum Status {
    Deleted
}
""")
        # Only one error reported per unique duplicate name
        messages = _messages(errors)
        assert messages.count("Duplicate enum name 'Status'") == 1

    def test_multiple_duplicates_in_same_file(self) -> None:
        errors = _analyze("""
enum Status {
    Active
}
enum Status {
    Inactive
}
type Address { field x: String }
type Address { field y: String }
""")
        messages = _messages(errors)
        assert any("Duplicate enum name 'Status'" in m for m in messages)
        assert any("Duplicate type name 'Address'" in m for m in messages)


# ###############
# Duplicate Enum Values
# ###############


class TestDuplicateEnumValues:
    def test_duplicate_enum_value(self) -> None:
        _assert_error(
            """
enum Status {
    Active
    Inactive
    Active
}
""",
            "Duplicate value 'Active' in enum 'Status'",
        )

    def test_no_duplicates_ok(self) -> None:
        _assert_clean("""
enum Status {
    Active
    Inactive
    Deleted
}
""")

    def test_duplicate_in_one_enum_not_other(self) -> None:
        errors = _analyze("""
enum A {
    X
    X
    Y
}
enum B {
    X
    Y
    Z
}
""")
        messages = _messages(errors)
        assert any("in enum 'A'" in m for m in messages)
        assert not any("in enum 'B'" in m for m in messages)

    def test_triple_duplicate_reports_once(self) -> None:
        errors = _analyze("""
enum Foo {
    A
    A
    A
}
""")
        messages = _messages(errors)
        assert messages.count("Duplicate value 'A' in enum 'Foo'") == 1


# ###############
# Duplicate Field Names
# ###############


class TestDuplicateFieldNames:
    def test_duplicate_field_in_type(self) -> None:
        _assert_error(
            """
type Address {
    field street: String
    field city: String
    field street: String
}
""",
            "Duplicate field name 'street' in type 'Address'",
        )

    def test_duplicate_field_in_interface(self) -> None:
        _assert_error(
            """
interface OrderRequest {
    field order_id: String
    field order_id: Int
}
""",
            "Duplicate field name 'order_id' in interface 'OrderRequest'",
        )

    def test_no_duplicate_fields_ok(self) -> None:
        _assert_clean("""
type Payload {
    field id: String
    field value: Int
    field active: Bool
}
""")

    def test_same_field_name_in_different_types_ok(self) -> None:
        _assert_clean("""
type A { field name: String }
type B { field name: Int }
""")


# ###############
# Named Type Reference Resolution
# ###############


class TestTypeReferenceResolution:
    def test_undefined_named_type_in_type_field(self) -> None:
        _assert_error(
            """
type Order {
    field status: OrderStatus
}
""",
            "Undefined type 'OrderStatus'",
        )

    def test_undefined_named_type_in_interface_field(self) -> None:
        _assert_error(
            """
interface Request {
    field item: OrderItem
}
""",
            "Undefined type 'OrderItem'",
        )

    def test_enum_used_as_field_type_ok(self) -> None:
        _assert_clean("""
enum Status {
    Active
}
type Record { field status: Status }
""")

    def test_type_used_as_field_type_ok(self) -> None:
        _assert_clean("""
type Item { field name: String }
type Order { field item: Item }
""")

    def test_interface_used_as_field_type_ok(self) -> None:
        _assert_clean("""
interface Config { field host: String }
type Spec { field config: Config }
""")

    def test_undefined_type_in_list(self) -> None:
        _assert_error(
            """
interface Batch {
    field items: List<UnknownItem>
}
""",
            "Undefined type 'UnknownItem'",
        )

    def test_undefined_key_in_map(self) -> None:
        _assert_error(
            """
interface Catalog {
    field entries: Map<BadKey, String>
}
""",
            "Undefined type 'BadKey'",
        )

    def test_undefined_value_in_map(self) -> None:
        _assert_error(
            """
interface Catalog {
    field entries: Map<String, BadValue>
}
""",
            "Undefined type 'BadValue'",
        )

    def test_undefined_type_in_optional(self) -> None:
        _assert_error(
            """
interface Response {
    field meta: Optional<UnknownMeta>
}
""",
            "Undefined type 'UnknownMeta'",
        )

    def test_known_type_via_import_ok(self) -> None:
        # Without resolved_imports, a type imported by name is accepted.
        _assert_clean("""
from types import OrderItem

interface Basket {
    field items: List<OrderItem>
}
""")

    def test_primitive_types_always_valid(self) -> None:
        _assert_clean("""
interface AllPrimitives {
    field a: String
    field b: Int
    field c: Float
    field d: Decimal
    field e: Bool
    field f: Bytes
    field g: Timestamp
    field h: Datetime
}
""")


# ###############
# Interface Reference Resolution
# ###############


class TestInterfaceRefResolution:
    def test_undefined_interface_in_requires(self) -> None:
        _assert_error(
            """
component Foo {
    requires UnknownInterface
}
""",
            "refers to unknown interface 'UnknownInterface'",
        )

    def test_undefined_interface_in_provides(self) -> None:
        _assert_error(
            """
component Foo {
    provides UnknownInterface
}
""",
            "refers to unknown interface 'UnknownInterface'",
        )

    def test_valid_interface_ref(self) -> None:
        _assert_clean("""
interface OrderRequest { field id: String }
component OrderService {
    requires OrderRequest
}
""")

    def test_interface_ref_resolved_via_import(self) -> None:
        # Without resolved_imports, any imported name is accepted as an interface.
        _assert_clean("""
from interfaces/order import OrderRequest
component OrderService {
    requires OrderRequest
}
""")

    def test_wrong_interface_version_local(self) -> None:
        _assert_error(
            """
interface OrderRequest @v2 { field id: String }
component OrderService {
    requires OrderRequest @v1
}
""",
            "no version 'v1' of interface 'OrderRequest' is defined",
        )

    def test_correct_versioned_ref_ok(self) -> None:
        _assert_clean("""
interface OrderRequest @v2 { field id: String }
component OrderService {
    requires OrderRequest @v2
}
""")

    def test_unversioned_ref_to_versioned_interface_ok(self) -> None:
        # Unversioned ref is accepted; the validation layer resolves to latest.
        _assert_clean("""
interface OrderRequest @v2 { field id: String }
component OrderService {
    requires OrderRequest
}
""")

    def test_versioned_ref_to_unversioned_interface_error(self) -> None:
        _assert_error(
            """
interface OrderRequest { field id: String }
component OrderService {
    requires OrderRequest @v1
}
""",
            "no version 'v1' of interface 'OrderRequest' is defined",
        )

    def test_system_with_undefined_requires(self) -> None:
        _assert_error(
            """
system Foo {
    requires MissingInterface
}
""",
            "refers to unknown interface 'MissingInterface'",
        )

    def test_system_with_undefined_provides(self) -> None:
        _assert_error(
            """
system Foo {
    provides MissingInterface
}
""",
            "refers to unknown interface 'MissingInterface'",
        )


# ###############
# Channel Validation
# ###############


class TestConnectValidation:
    def test_valid_system_connect(self) -> None:
        _assert_clean("""
interface DataFeed { field payload: String }
system Pipeline {
    component Producer { provides DataFeed }
    component Consumer { requires DataFeed }
    connect Producer.DataFeed -> $feed -> Consumer.DataFeed
}
""")

    def test_valid_component_connect(self) -> None:
        _assert_clean("""
interface Signal { field value: Int }
component Processor {
    component Source { provides Signal }
    component Sink { requires Signal }
    connect Source.Signal -> $sig -> Sink.Signal
}
""")

    def test_connect_with_unknown_src_entity(self) -> None:
        _assert_error(
            """
interface DataFeed { field payload: String }
system Pipeline {
    component Consumer { requires DataFeed }
    connect Ghost.DataFeed -> $feed -> Consumer.DataFeed
}
""",
            "connect references unknown child entity 'Ghost'",
        )

    def test_connect_with_unknown_dst_entity(self) -> None:
        _assert_error(
            """
interface DataFeed { field payload: String }
system Pipeline {
    component Producer { provides DataFeed }
    connect Producer.DataFeed -> $feed -> Ghost.DataFeed
}
""",
            "connect references unknown child entity 'Ghost'",
        )

    def test_expose_with_unknown_entity(self) -> None:
        _assert_error(
            """
interface Signal { field v: Bool }
component Router {
    component Input { provides Signal }
    expose Missing.Signal
}
""",
            "expose references unknown child entity 'Missing'",
        )

    def test_valid_expose(self) -> None:
        _assert_clean("""
interface Signal { field value: Bool }
component Router {
    component Input { provides Signal }
    expose Input.Signal
}
""")

    def test_expose_with_unknown_port(self) -> None:
        """Exposing a port name that does not exist on the child entity is an error."""
        _assert_error(
            """
interface Signal { field v: Bool }
component Router {
    component Input { provides Signal }
    expose Input.Typo
}
""",
            "expose references unknown port 'Typo' on 'Input'",
        )

    def test_expose_requires_port_is_valid(self) -> None:
        """Exposing a requires port (not just provides) is valid."""
        _assert_clean("""
interface Signal { field value: Bool }
component Router {
    component Output { requires Signal }
    expose Output.Signal
}
""")

    def test_expose_of_re_exposed_port_is_valid(self) -> None:
        """A port promoted via expose is valid as a target of an outer expose."""
        _assert_clean("""
interface OrderRequest { field id: String }
interface Simple { field val: Int }
system Order {
    component A {
        component SubA1 { requires OrderRequest }
        component SubA2 { provides Simple }
        expose SubA1.OrderRequest
        expose SubA2.Simple
    }
    expose A.OrderRequest
    expose A.Simple
}
""")

    def test_direct_connect_no_channel(self) -> None:
        _assert_error(
            """
interface DataFeed { field payload: String }
system Pipeline {
    component Producer { provides DataFeed }
    component Consumer { requires DataFeed }
    connect Producer.DataFeed -> Consumer.DataFeed
}
""",
            "connect without a channel is not allowed",
        )


# ###############
# Duplicate Nested Names
# ###############


class TestDuplicateNestedNames:
    def test_duplicate_sub_component_in_component(self) -> None:
        _assert_error(
            """
component Router {
    component Leg {}
    component Leg {}
}
""",
            "Duplicate sub-component name 'Leg'",
        )

    def test_duplicate_component_in_system(self) -> None:
        _assert_error(
            """
system Platform {
    component Worker {}
    component Worker {}
}
""",
            "Duplicate component name 'Worker'",
        )

    def test_duplicate_sub_system_in_system(self) -> None:
        _assert_error(
            """
system Enterprise {
    system Division {}
    system Division {}
}
""",
            "Duplicate sub-system name 'Division'",
        )

    def test_component_and_system_same_name_in_system(self) -> None:
        _assert_error(
            """
system Enterprise {
    component Foo {}
    system Foo {}
}
""",
            "name 'Foo' is used for both a component and a sub-system",
        )

    def test_distinct_sub_component_names_ok(self) -> None:
        _assert_clean("""
component Router {
    component InputHandler {}
    component OutputHandler {}
}
""")


# ###############
# Import Resolution
# ###############


class TestImportResolution:
    def test_entity_not_found_in_resolved_file(self) -> None:
        source_file = parse("interface RealInterface { field x: String }")
        errors = _analyze(
            "from interfaces/order import MissingInterface",
            resolved_imports={"interfaces/order": source_file},
        )
        assert any("'MissingInterface' is not defined in 'interfaces/order'" in e.message for e in errors)

    def test_import_source_not_in_resolved(self) -> None:
        errors = _analyze(
            "from missing/path import SomeEntity",
            resolved_imports={},
        )
        assert any("'missing/path' could not be resolved" in e.message for e in errors)

    def test_valid_import_resolution(self) -> None:
        source_file = parse("""
interface OrderRequest { field id: String }
type OrderItem { field name: String }
""")
        _assert_clean(
            "from types import OrderRequest, OrderItem",
            resolved_imports={"types": source_file},
        )

    def test_no_errors_without_resolved_imports(self) -> None:
        # Without resolved_imports, import validation is skipped.
        _assert_clean("from missing/path import SomeEntity")

    def test_partial_import_failure(self) -> None:
        source_file = parse("interface Real { field x: String }")
        errors = _analyze(
            "from src import Real, Missing",
            resolved_imports={"src": source_file},
        )
        messages = _messages(errors)
        assert any("'Missing' is not defined in 'src'" in m for m in messages)
        assert not any("'Real' is not defined" in m for m in messages)

    def test_imported_component_found_in_resolved(self) -> None:
        source_file = parse("component OrderService {}")
        _assert_clean(
            "from services/order import OrderService",
            resolved_imports={"services/order": source_file},
        )

    def test_imported_system_found_in_resolved(self) -> None:
        source_file = parse("system ECommerce {}")
        _assert_clean(
            "from systems/ecommerce import ECommerce",
            resolved_imports={"systems/ecommerce": source_file},
        )

    def test_imported_enum_found_in_resolved(self) -> None:
        source_file = parse("enum Status {\n    Active\n    Inactive\n}")
        _assert_clean(
            "from enums import Status",
            resolved_imports={"enums": source_file},
        )

    def test_multiple_import_sources_one_missing(self) -> None:
        source_file = parse("interface Foo { field x: String }")
        errors = _analyze(
            """
from known/path import Foo
from unknown/path import Bar
""",
            resolved_imports={"known/path": source_file},
        )
        messages = _messages(errors)
        assert any("'unknown/path' could not be resolved" in m for m in messages)
        assert not any("'known/path' could not be resolved" in m for m in messages)


# ###############
# Direct Model Construction Tests
# ###############


class TestDirectModelConstruction:
    """Tests using directly constructed ArchFile models for fine-grained checks."""

    def test_analyze_empty_arch_file(self) -> None:
        arch_file = ArchFile()
        assert analyze(arch_file) == []

    def test_duplicate_enum_names_in_model(self) -> None:
        arch_file = ArchFile(
            enums=[
                EnumDef(name="Status", values=["A"]),
                EnumDef(name="Status", values=["B"]),
            ]
        )
        errors = analyze(arch_file)
        assert any("Duplicate enum name 'Status'" in e.message for e in errors)

    def test_connect_with_known_interface_model(self) -> None:
        arch_file = ArchFile(
            interfaces=[InterfaceDef(name="Signal", version=None)],
            systems=[
                System(
                    name="Sys",
                    connects=[
                        ConnectDef(
                            src_entity="A",
                            src_port="Signal",
                            channel="sig",
                            dst_entity="B",
                            dst_port="Signal",
                        )
                    ],
                    components=[
                        Component(name="A", provides=[InterfaceRef(name="Signal")]),
                        Component(name="B", requires=[InterfaceRef(name="Signal")]),
                    ],
                )
            ],
        )
        assert analyze(arch_file) == []

    def test_field_with_named_type_ref_resolved_from_imports(self) -> None:
        from archml.model.entities import ImportDeclaration

        arch_file = ArchFile(
            imports=[ImportDeclaration(source_path="types", entities=["Item"])],
            interfaces=[
                InterfaceDef(
                    name="Batch",
                    fields=[
                        FieldDef(
                            name="items",
                            type=ListTypeRef(element_type=NamedTypeRef(name="Item")),
                        )
                    ],
                )
            ],
        )
        # Without resolved_imports: Item is "imported", no error
        errors = analyze(arch_file)
        assert not any("Undefined type 'Item'" in e.message for e in errors)

    def test_field_with_completely_unknown_type(self) -> None:
        arch_file = ArchFile(
            interfaces=[
                InterfaceDef(
                    name="Batch",
                    fields=[FieldDef(name="items", type=NamedTypeRef(name="UnknownType"))],
                )
            ],
        )
        errors = analyze(arch_file)
        assert any("Undefined type 'UnknownType'" in e.message for e in errors)


# ###############
# Duplicate Import Names
# ###############


class TestDuplicateImportNames:
    """Tests that the same entity name imported from multiple sources fails."""

    def test_same_name_from_two_different_sources_fails(self) -> None:
        _assert_error(
            """
from interfaces/order import OrderRequest
from interfaces/other import OrderRequest
""",
            "Duplicate import name 'OrderRequest'",
        )

    def test_same_name_from_same_source_twice_fails(self) -> None:
        _assert_error(
            """
from interfaces/order import OrderRequest
from interfaces/order import OrderRequest
""",
            "Duplicate import name 'OrderRequest'",
        )

    def test_different_names_from_different_sources_ok(self) -> None:
        _assert_clean("""
from interfaces/order import OrderRequest
from interfaces/payment import PaymentRequest
""")

    def test_different_names_from_same_source_ok(self) -> None:
        _assert_clean("""
from interfaces/order import OrderRequest, PaymentRequest
""")

    def test_duplicate_within_single_import_statement_fails(self) -> None:
        # Parser allows this, but semantic analysis must reject it.
        from archml.model.entities import ImportDeclaration

        arch_file = ArchFile(
            imports=[
                ImportDeclaration(source_path="interfaces/order", entities=["Foo", "Foo"]),
            ]
        )
        errors = analyze(arch_file)
        assert any("Duplicate import name 'Foo'" in e.message for e in errors)

    def test_error_message_names_both_sources(self) -> None:
        errors = _analyze("""
from path/a import MyInterface
from path/b import MyInterface
""")
        messages = _messages(errors)
        assert any("'path/a'" in m and "'path/b'" in m for m in messages)

    def test_multiple_duplicate_imports_reported(self) -> None:
        errors = _analyze("""
from path/a import Foo
from path/b import Bar
from path/c import Foo
from path/d import Bar
""")
        messages = _messages(errors)
        assert any("Duplicate import name 'Foo'" in m for m in messages)
        assert any("Duplicate import name 'Bar'" in m for m in messages)

    def test_duplicate_import_does_not_prevent_other_error_detection(self) -> None:
        # A duplicate import name is flagged alongside any other errors.
        errors = _analyze("""
from path/a import Foo
from path/b import Foo
component Bar {
    requires UnknownInterface
}
""")
        messages = _messages(errors)
        assert any("Duplicate import name 'Foo'" in m for m in messages)
        assert any("refers to unknown interface 'UnknownInterface'" in m for m in messages)


# ###############
# Qualified Names
# ###############


class TestQualifiedNames:
    """Tests that fully-qualified names are correctly assigned to entities."""

    def test_top_level_component_has_local_name_as_qualified_name(self) -> None:
        arch_file = parse("component Worker {}")
        analyze(arch_file)
        assert arch_file.components[0].qualified_name == "Worker"

    def test_top_level_system_has_local_name_as_qualified_name(self) -> None:
        arch_file = parse("system Enterprise {}")
        analyze(arch_file)
        assert arch_file.systems[0].qualified_name == "Enterprise"

    def test_top_level_interface_has_local_name_as_qualified_name(self) -> None:
        arch_file = parse("interface OrderRequest { field id: String }")
        analyze(arch_file)
        assert arch_file.interfaces[0].qualified_name == "OrderRequest"

    def test_versioned_interface_qualified_name_includes_version(self) -> None:
        arch_file = parse("interface OrderRequest @v2 { field id: String }")
        analyze(arch_file)
        assert arch_file.interfaces[0].qualified_name == "OrderRequest@v2"

    def test_component_in_system_gets_coloncolon_qualified_name(self) -> None:
        arch_file = parse("""
system SystemA {
    component Worker {}
}
""")
        analyze(arch_file)
        system = arch_file.systems[0]
        assert system.qualified_name == "SystemA"
        assert system.components[0].qualified_name == "SystemA::Worker"

    def test_same_named_components_in_different_systems_get_distinct_qualified_names(self) -> None:
        arch_file = parse("""
system SystemA {
    component Worker {}
}

system SystemB {
    component Worker {}
}
""")
        errors = analyze(arch_file)
        assert errors == [], f"Expected no errors but got: {[e.message for e in errors]}"
        assert arch_file.systems[0].components[0].qualified_name == "SystemA::Worker"
        assert arch_file.systems[1].components[0].qualified_name == "SystemB::Worker"

    def test_nested_sub_system_gets_coloncolon_qualified_name(self) -> None:
        arch_file = parse("""
system Enterprise {
    system Division {}
}
""")
        analyze(arch_file)
        enterprise = arch_file.systems[0]
        assert enterprise.qualified_name == "Enterprise"
        assert enterprise.systems[0].qualified_name == "Enterprise::Division"

    def test_deeply_nested_component_gets_full_coloncolon_path(self) -> None:
        arch_file = parse("""
system Enterprise {
    system Division {
        component Worker {}
    }
}
""")
        analyze(arch_file)
        enterprise = arch_file.systems[0]
        division = enterprise.systems[0]
        worker = division.components[0]
        assert enterprise.qualified_name == "Enterprise"
        assert division.qualified_name == "Enterprise::Division"
        assert worker.qualified_name == "Enterprise::Division::Worker"

    def test_nested_sub_component_gets_coloncolon_qualified_name(self) -> None:
        arch_file = parse("""
component Router {
    component InputHandler {}
    component OutputHandler {}
}
""")
        analyze(arch_file)
        router = arch_file.components[0]
        assert router.qualified_name == "Router"
        assert router.components[0].qualified_name == "Router::InputHandler"
        assert router.components[1].qualified_name == "Router::OutputHandler"

    def test_file_key_prefixes_top_level_component(self) -> None:
        arch_file = parse("component Worker {}")
        analyze(arch_file, file_key="myapp/services")
        assert arch_file.components[0].qualified_name == "myapp/services::Worker"

    def test_file_key_prefixes_top_level_system(self) -> None:
        arch_file = parse("system Enterprise {}")
        analyze(arch_file, file_key="myapp/core")
        assert arch_file.systems[0].qualified_name == "myapp/core::Enterprise"

    def test_file_key_prefixes_top_level_interface(self) -> None:
        arch_file = parse("interface OrderRequest { field id: String }")
        analyze(arch_file, file_key="myapp/types")
        assert arch_file.interfaces[0].qualified_name == "myapp/types::OrderRequest"

    def test_file_key_prefixes_versioned_interface(self) -> None:
        arch_file = parse("interface OrderRequest @v2 { field id: String }")
        analyze(arch_file, file_key="myapp/types")
        assert arch_file.interfaces[0].qualified_name == "myapp/types::OrderRequest@v2"

    def test_file_key_propagates_through_nested_entities(self) -> None:
        arch_file = parse("""
system Enterprise {
    system Division {
        component Worker {}
    }
}
""")
        analyze(arch_file, file_key="myapp/services")
        enterprise = arch_file.systems[0]
        division = enterprise.systems[0]
        worker = division.components[0]
        assert enterprise.qualified_name == "myapp/services::Enterprise"
        assert division.qualified_name == "myapp/services::Enterprise::Division"
        assert worker.qualified_name == "myapp/services::Enterprise::Division::Worker"

    def test_remote_file_key_prefix(self) -> None:
        arch_file = parse("component Lib {}")
        analyze(arch_file, file_key="@payments/lib/shared")
        assert arch_file.components[0].qualified_name == "@payments/lib/shared::Lib"

    def test_same_named_components_in_different_scopes_no_errors(self) -> None:
        # 'component' appears in both SystemA and SystemB — this must not
        # produce a duplicate-name error.
        _assert_clean("""
system SystemA {
    component Service {}
}

system SystemB {
    component Service {}
}
""")

    def test_same_named_sub_components_in_different_parent_components_no_errors(self) -> None:
        _assert_clean("""
component RouterA {
    component Handler {}
}

component RouterB {
    component Handler {}
}
""")

    def test_multiple_top_level_interfaces_with_same_name_from_different_files_represented_distinctly(
        self,
    ) -> None:
        # Each file independently defines its own interface; the qualified name
        # is simply the local name (possibly with version).  Distinguishing
        # interfaces across files is the responsibility of the import system
        # (duplicate import names are rejected).
        arch_file = parse("""
interface Foo { field x: String }
interface Foo @v2 { field x: String }
""")
        analyze(arch_file)
        assert arch_file.interfaces[0].qualified_name == "Foo"
        assert arch_file.interfaces[1].qualified_name == "Foo@v2"


# ###############
# User Checks
# ###############


class TestUserSemantics:
    def test_user_with_valid_interface_refs(self) -> None:
        _assert_clean("""
interface OrderRequest {}
interface OrderConfirmation {}
user Customer {
    provides OrderRequest
    requires OrderConfirmation
}
""")

    def test_user_unknown_requires_interface(self) -> None:
        _assert_error(
            "user Customer { requires Unknown }",
            "unknown interface 'Unknown'",
        )

    def test_user_unknown_provides_interface(self) -> None:
        _assert_error(
            "user Customer { provides Unknown }",
            "unknown interface 'Unknown'",
        )

    def test_duplicate_top_level_user(self) -> None:
        _assert_error(
            "user A {} user A {}",
            "Duplicate user name 'A'",
        )

    def test_duplicate_user_in_system(self) -> None:
        _assert_error(
            "system S { user A {} user A {} }",
            "Duplicate user name 'A'",
        )

    def test_user_name_conflicts_with_component_in_system(self) -> None:
        _assert_error(
            "system S { component A {} user A {} }",
            "name 'A' is used for both a user and a component or sub-system",
        )

    def test_user_name_conflicts_with_system_in_system(self) -> None:
        _assert_error(
            "system S { system Sub {} user Sub {} }",
            "name 'Sub' is used for both a user and a component or sub-system",
        )

    def test_user_provides_connected_in_system(self) -> None:
        _assert_clean("""
interface OrderRequest {}
system S {
    user Customer { provides OrderRequest }
    component OrderService { requires OrderRequest }
    connect Customer.OrderRequest -> $orders -> OrderService.OrderRequest
}
""")

    def test_user_without_via_is_valid(self) -> None:
        _assert_clean("""
interface I {}
user A { provides I }
component B { requires I }
""")

    def test_user_qualified_name_top_level(self) -> None:
        arch_file = parse("user Customer {}")
        analyze(arch_file, file_key="myapp/actors")
        assert arch_file.users[0].qualified_name == "myapp/actors::Customer"

    def test_user_qualified_name_no_file_key(self) -> None:
        arch_file = parse("user Customer {}")
        analyze(arch_file)
        assert arch_file.users[0].qualified_name == "Customer"

    def test_user_qualified_name_in_system(self) -> None:
        arch_file = parse("system S { user Customer {} }")
        analyze(arch_file)
        assert arch_file.systems[0].users[0].qualified_name == "S::Customer"

    def test_external_user_valid(self) -> None:
        _assert_clean("""
interface I {}
external user ExternalClient { provides I }
""")

    def test_user_versioned_interface_ref(self) -> None:
        _assert_clean("""
interface I @v2 {}
user Customer { requires I @v2 }
""")


# ###############
# Port Name Uniqueness
# ###############


class TestPortNameUniqueness:
    def test_duplicate_implicit_port_name_in_component(self) -> None:
        _assert_error(
            """
interface Foo { field x: String }
component Bar {
    requires Foo
    provides Foo
}
""",
            "Duplicate port name 'Foo' in component 'Bar'",
        )

    def test_duplicate_explicit_port_name_in_component(self) -> None:
        _assert_error(
            """
interface Foo { field x: String }
interface Baz { field y: Int }
component Bar {
    requires Foo as my_port
    provides Baz as my_port
}
""",
            "Duplicate port name 'my_port' in component 'Bar'",
        )

    def test_duplicate_mixed_implicit_explicit_port_name(self) -> None:
        _assert_error(
            """
interface Foo { field x: String }
interface Baz { field y: Int }
component Bar {
    requires Foo
    provides Baz as Foo
}
""",
            "Duplicate port name 'Foo' in component 'Bar'",
        )

    def test_duplicate_requires_port_names_in_component(self) -> None:
        _assert_error(
            """
interface Foo { field x: String }
interface Bar { field y: Int }
component Comp {
    requires Foo
    requires Bar as Foo
}
""",
            "Duplicate port name 'Foo' in component 'Comp'",
        )

    def test_unique_port_names_ok(self) -> None:
        _assert_clean("""
interface Foo { field x: String }
interface Baz { field y: Int }
component Bar {
    requires Foo as in_port
    provides Baz as out_port
}
""")

    def test_different_interfaces_different_names_ok(self) -> None:
        _assert_clean("""
interface Foo { field x: String }
interface Bar { field y: Int }
component Comp {
    requires Foo
    provides Bar
}
""")

    def test_duplicate_port_name_in_system(self) -> None:
        _assert_error(
            """
interface Foo { field x: String }
system Sys {
    requires Foo
    provides Foo
}
""",
            "Duplicate port name 'Foo' in system 'Sys'",
        )

    def test_duplicate_port_name_in_user(self) -> None:
        _assert_error(
            """
interface Foo { field x: String }
user Alice {
    requires Foo
    provides Foo
}
""",
            "Duplicate port name 'Foo' in user 'Alice'",
        )

    def test_duplicate_port_name_in_nested_component(self) -> None:
        _assert_error(
            """
interface Sig { field v: Bool }
component Outer {
    component Inner {
        requires Sig
        provides Sig
    }
}
""",
            "Duplicate port name 'Sig' in component 'Inner'",
        )

    def test_duplicate_port_name_in_system_nested_component(self) -> None:
        _assert_error(
            """
interface Sig { field v: Bool }
system Sys {
    component Worker {
        requires Sig
        provides Sig
    }
}
""",
            "Duplicate port name 'Sig' in component 'Worker'",
        )


# ###############
# Top-level connects
# ###############


class TestTopLevelConnect:
    def test_valid_top_level_connect_full_form(self) -> None:
        """connect at file scope with full Entity.port notation is valid."""
        _assert_clean("""
interface API { field endpoint: String }
system Frontend { provides API }
system Backend { requires API }

connect Frontend.API -> $bus -> Backend.API
""")

    def test_top_level_connect_unknown_src_entity(self) -> None:
        """Top-level connect referencing a missing src entity is an error."""
        _assert_error(
            """
interface API { field endpoint: String }
system Backend { requires API }

connect Ghost.API -> $bus -> Backend.API
""",
            "connect references unknown child entity 'Ghost'",
        )

    def test_top_level_connect_unknown_dst_entity(self) -> None:
        """Top-level connect referencing a missing dst entity is an error."""
        _assert_error(
            """
interface API { field endpoint: String }
system Frontend { provides API }

connect Frontend.API -> $bus -> Ghost.API
""",
            "connect references unknown child entity 'Ghost'",
        )

    def test_top_level_connect_between_systems_and_components(self) -> None:
        """Top-level connects can reference any top-level entity (system or component)."""
        _assert_clean("""
interface Data { field v: String }
system Upstream { provides Data }
component Sink { requires Data }

connect Upstream.Data -> $pipe -> Sink.Data
""")

    def test_top_level_connect_unknown_src_port(self) -> None:
        """A typo in the src port of a top-level connect is a semantic error."""
        _assert_error(
            """
interface API { field endpoint: String }
system Frontend { provides API }
system Backend { requires API }

connect Frontend.Typo -> $bus -> Backend.API
""",
            "connect references unknown port 'Typo' on 'Frontend'",
        )

    def test_top_level_connect_unknown_dst_port(self) -> None:
        """A typo in the dst port of a top-level connect is a semantic error."""
        _assert_error(
            """
interface API { field endpoint: String }
system Frontend { provides API }
system Backend { requires API }

connect Frontend.API -> $bus -> Backend.Typo
""",
            "connect references unknown port 'Typo' on 'Backend'",
        )

    def test_top_level_connect_exposed_port_is_valid(self) -> None:
        """A port that is exposed by a child system is valid in a top-level connect."""
        _assert_clean("""
interface OrderRequest { }
interface OrderConfirmation { }
interface Simple { }

system Order {
    component A { requires OrderRequest  provides Simple }
    component B { requires Simple  provides OrderConfirmation }
    connect A.Simple -> $ch -> B.Simple
    expose A.OrderRequest
    expose B.OrderConfirmation
}
external system Source { provides OrderRequest }
external system Sink { requires OrderConfirmation }

connect Source.OrderRequest -> $req -> Order.OrderRequest
connect Order.OrderConfirmation -> $conf -> Sink.OrderConfirmation
""")

    def test_top_level_connect_typo_in_exposed_port_is_error(self) -> None:
        """Typo in an exposed port name (as seen in user's archml file) is caught."""
        _assert_error(
            """
interface OrderConfirmation { }
interface Simple { }

system Order {
    component B { requires Simple  provides OrderConfirmation }
    expose B.OrderConfirmation
}
external system Sink { requires OrderConfirmation }
component Src { provides Simple }

connect Order.OrderConfirmtion -> $conf -> Sink.OrderConfirmation
""",
            "connect references unknown port 'OrderConfirmtion' on 'Order'",
        )

    def test_inner_connect_unknown_port(self) -> None:
        """Unknown port name in an inner connect (within a system) is an error."""
        _assert_error(
            """
interface Data { field v: String }
system S {
    component A { provides Data }
    component B { requires Data }
    connect A.Typo -> $ch -> B.Data
}
""",
            "connect references unknown port 'Typo' on 'A'",
        )


# ###############
# Simplified connect form
# ###############


class TestSimplifiedConnect:
    def test_simplified_connect_resolves_unique_ports(self) -> None:
        """Simplified form A -> $ch -> B resolves to full form when ports are unique."""
        source = """
interface DataFeed { field payload: String }
system Pipeline {
    component Producer { provides DataFeed }
    component Consumer { requires DataFeed }
    connect Producer -> $feed -> Consumer
}
"""
        file = parse(source)
        errors = analyze(file)
        assert errors == []
        conn = file.systems[0].connects[0]
        # Simplified form is resolved in-place during semantic analysis.
        assert conn.src_entity == "Producer"
        assert conn.src_port == "DataFeed"
        assert conn.dst_entity == "Consumer"
        assert conn.dst_port == "DataFeed"

    def test_simplified_connect_one_sided_src(self) -> None:
        """Simplified form A -> $ch resolves src port when unique."""
        source = """
interface Signal { field v: Bool }
system S {
    component Sender { provides Signal }
    connect Sender -> $sig
}
"""
        file = parse(source)
        errors = analyze(file)
        assert errors == []
        conn = file.systems[0].connects[0]
        assert conn.src_entity == "Sender"
        assert conn.src_port == "Signal"
        assert conn.dst_entity is None

    def test_simplified_connect_one_sided_dst(self) -> None:
        """Simplified form $ch -> B resolves dst port when unique."""
        source = """
interface Signal { field v: Bool }
system S {
    component Receiver { requires Signal }
    connect $sig -> Receiver
}
"""
        file = parse(source)
        errors = analyze(file)
        assert errors == []
        conn = file.systems[0].connects[0]
        assert conn.src_entity is None
        assert conn.dst_entity == "Receiver"
        assert conn.dst_port == "Signal"

    def test_simplified_connect_ambiguous_src_port_error(self) -> None:
        """Simplified form on an entity with multiple provides ports is an error."""
        _assert_error(
            """
interface A { field v: String }
interface B { field v: String }
system S {
    component Multi { provides A  provides B }
    component Sink { requires A }
    connect Multi -> $ch -> Sink
}
""",
            "simplified connect: 'Multi' has multiple provides ports",
        )

    def test_simplified_connect_no_src_port_error(self) -> None:
        """Simplified form on an entity with no provides ports is an error."""
        _assert_error(
            """
interface A { field v: String }
system S {
    component NoOut {}
    component Sink { requires A }
    connect NoOut -> $ch -> Sink
}
""",
            "simplified connect: 'NoOut' has no provides ports",
        )

    def test_simplified_connect_top_level_resolution(self) -> None:
        """Simplified form resolves correctly at the top-level file scope."""
        source = """
interface API { field endpoint: String }
system Frontend { provides API }
system Backend { requires API }

connect Frontend -> $bus -> Backend
"""
        file = parse(source)
        errors = analyze(file)
        assert errors == []
        conn = file.connects[0]
        assert conn.src_entity == "Frontend"
        assert conn.src_port == "API"
        assert conn.dst_entity == "Backend"
        assert conn.dst_port == "API"


# ###############################################
# Local interface definitions in components/systems
# ###############################################


class TestLocalInterfaceInComponent:
    """Tests for interface definitions nested inside component bodies."""

    def test_local_interface_parsed_and_no_errors(self) -> None:
        """A locally defined interface is accepted and usable within the component."""
        errors = _analyze("""
component A {
    interface AInternal {
        field id: Int
    }
    component SubA1 {
        provides AInternal
    }
    component SubA2 {
        requires AInternal
    }
    connect SubA1 -> $internal -> SubA2
}
""")
        assert errors == []

    def test_local_interface_not_visible_outside_component(self) -> None:
        """A locally defined interface is not in scope outside its defining component."""
        errors = _analyze("""
component A {
    interface AInternal {
        field id: Int
    }
}
component B {
    requires AInternal
}
""")
        assert any("unknown interface 'AInternal'" in e.message for e in errors)

    def test_local_interface_qualified_name_assigned(self) -> None:
        """Qualified names are assigned to local interfaces using the component path."""
        src = """
component A {
    interface Inner {
        field x: String
    }
}
"""
        af = parse(src)
        analyze(af)
        assert af.components[0].interfaces[0].qualified_name == "A::Inner"

    def test_duplicate_local_interface_in_component(self) -> None:
        """Duplicate local interface names within a component are reported."""
        errors = _analyze("""
component A {
    interface Foo { field x: Int }
    interface Foo { field y: String }
}
""")
        assert any("Duplicate local interface name 'Foo'" in e.message for e in errors)

    def test_local_interface_with_file_key(self) -> None:
        """Qualified names include the file key prefix for local interfaces."""
        src = """
component A {
    interface Inner { field x: Int }
}
"""
        af = parse(src)
        analyze(af, file_key="myapp/services")
        assert af.components[0].interfaces[0].qualified_name == "myapp/services::A::Inner"

    def test_local_interface_used_by_own_requires_provides(self) -> None:
        """The parent component itself can use its own locally defined interface."""
        errors = _analyze("""
component A {
    interface AOut { field result: String }
    provides AOut
}
""")
        assert errors == []


class TestLocalInterfaceInSystem:
    """Tests for interface definitions nested inside system bodies."""

    def test_local_interface_in_system_no_errors(self) -> None:
        """A locally defined interface in a system is accepted and usable by children."""
        errors = _analyze("""
system S {
    interface SInternal { field val: Int }
    component Producer { provides SInternal }
    component Consumer { requires SInternal }
    connect Producer -> $internal -> Consumer
}
""")
        assert errors == []

    def test_local_interface_in_system_not_visible_outside(self) -> None:
        """A locally defined interface in a system is not visible outside the system."""
        errors = _analyze("""
system S {
    interface SInternal { field val: Int }
}
component C {
    requires SInternal
}
""")
        assert any("unknown interface 'SInternal'" in e.message for e in errors)

    def test_local_interface_in_system_qualified_name(self) -> None:
        """Qualified names are assigned to local interfaces using the system path."""
        src = """
system S {
    interface Inner { field x: Int }
}
"""
        af = parse(src)
        analyze(af)
        assert af.systems[0].interfaces[0].qualified_name == "S::Inner"

    def test_duplicate_local_interface_in_system(self) -> None:
        """Duplicate local interface names within a system are reported."""
        errors = _analyze("""
system S {
    interface Dup { field x: Int }
    interface Dup { field y: String }
}
""")
        assert any("Duplicate local interface name 'Dup'" in e.message for e in errors)

    def test_local_interface_inherited_by_nested_system(self) -> None:
        """Local interface is in scope for a nested sub-system."""
        errors = _analyze("""
system Outer {
    interface Shared { field v: String }
    system Inner {
        component X { provides Shared }
        component Y { requires Shared }
        connect X -> $shared -> Y
    }
}
""")
        assert errors == []

    def test_user_in_example_scenario(self) -> None:
        """The original user-reported scenario compiles without errors."""
        errors = _analyze("""
interface OrderRequest { field order_id: Int }
interface Simple { field val: String }

component A {
    interface AInternal { field id: Int }

    component SubA1 {
        requires OrderRequest
        provides AInternal
    }

    component SubA2 {
        requires AInternal
        provides Simple
    }

    connect SubA1 -> $internal -> SubA2
}
""")
        assert errors == []


# ###############
# Artifact Semantics
# ###############


class TestArtifactSemantics:
    def test_artifact_is_valid_top_level_declaration(self) -> None:
        _assert_clean("artifact Report {}")

    def test_artifact_name_usable_as_field_type_in_type(self) -> None:
        _assert_clean("""\
artifact Report {}
type Order {
    field report: Report
}
""")

    def test_artifact_name_usable_as_field_type_in_interface(self) -> None:
        _assert_clean("""\
artifact Bundle {}
interface DeployRequest {
    field bundle: Bundle
}
""")

    def test_artifact_name_usable_inside_optional(self) -> None:
        _assert_clean("""\
artifact Report {}
type Order {
    field report: Optional<Report>
}
""")

    def test_artifact_name_usable_inside_list(self) -> None:
        _assert_clean("""\
artifact Report {}
type Batch {
    field reports: List<Report>
}
""")

    def test_duplicate_artifact_name_is_an_error(self) -> None:
        _assert_error(
            "artifact Dup {}\nartifact Dup {}",
            "Duplicate artifact name 'Dup'",
        )

    def test_artifact_name_clashing_with_type_name_is_an_error(self) -> None:
        _assert_error(
            "type Clash {}\nartifact Clash {}",
            "defined as both an artifact and an enum or type",
        )

    def test_artifact_name_clashing_with_enum_name_is_an_error(self) -> None:
        _assert_error(
            "enum Clash {\n    VAL\n}\nartifact Clash {}",
            "defined as both an artifact and an enum or type",
        )

    def test_imported_artifact_name_is_valid_field_type(self) -> None:
        from archml.model.entities import ArchFile, ArtifactDef

        resolved = {"artifacts": ArchFile(artifacts=[ArtifactDef(name="Bundle")])}
        _assert_clean(
            """\
from artifacts import Bundle
interface DeployRequest {
    field bundle: Bundle
}
""",
            resolved_imports=resolved,
        )

    def test_artifact_included_in_top_level_names_for_import_validation(self) -> None:
        from archml.model.entities import ArchFile, ArtifactDef

        resolved = {"artifacts": ArchFile(artifacts=[ArtifactDef(name="Report")])}
        _assert_clean(
            "from artifacts import Report",
            resolved_imports=resolved,
        )
