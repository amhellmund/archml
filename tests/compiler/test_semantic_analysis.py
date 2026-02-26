# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the ArchML semantic analysis module."""

from archml.compiler.parser import parse
from archml.compiler.semantic_analysis import SemanticError, analyze
from archml.model.entities import (
    ArchFile,
    Component,
    Connection,
    ConnectionEndpoint,
    EnumDef,
    InterfaceDef,
    InterfaceRef,
    System,
)
from archml.model.types import Field, ListTypeRef, NamedTypeRef

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


def _assert_error(source: str, expected_fragment: str, resolved_imports: dict[str, ArchFile] | None = None) -> None:
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

    def test_system_with_components_and_connection(self) -> None:
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

    connect Producer -> Consumer by DataFeed
}
""")

    def test_nested_components_with_connection(self) -> None:
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

    connect Input -> Output by Signal
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
        _assert_error("""
enum Status { Active }
enum Status { Inactive }
""", "Duplicate enum name 'Status'")

    def test_duplicate_type_name(self) -> None:
        _assert_error("""
type Address { field street: String }
type Address { field city: String }
""", "Duplicate type name 'Address'")

    def test_duplicate_component_name(self) -> None:
        _assert_error("""
component OrderService {}
component OrderService {}
""", "Duplicate component name 'OrderService'")

    def test_duplicate_system_name(self) -> None:
        _assert_error("""
system ECommerce {}
system ECommerce {}
""", "Duplicate system name 'ECommerce'")

    def test_duplicate_interface_same_name_no_version(self) -> None:
        _assert_error("""
interface OrderRequest { field a: String }
interface OrderRequest { field b: Int }
""", "Duplicate interface definition 'OrderRequest'")

    def test_duplicate_interface_same_name_same_version(self) -> None:
        _assert_error("""
interface OrderRequest @v2 { field a: String }
interface OrderRequest @v2 { field b: Int }
""", "Duplicate interface definition 'OrderRequest@v2'")

    def test_different_interface_versions_are_ok(self) -> None:
        _assert_clean("""
interface OrderRequest { field a: String }
interface OrderRequest @v2 { field b: Int }
""")

    def test_enum_and_type_same_name_conflict(self) -> None:
        _assert_error("""
enum Foo { Bar }
type Foo { field x: String }
""", "Name 'Foo' is defined as both an enum and a type")

    def test_third_occurrence_of_duplicate_name(self) -> None:
        errors = _analyze("""
enum Status { Active }
enum Status { Inactive }
enum Status { Deleted }
""")
        # Only one error reported per unique duplicate name
        messages = _messages(errors)
        assert messages.count("Duplicate enum name 'Status'") == 1

    def test_multiple_duplicates_in_same_file(self) -> None:
        errors = _analyze("""
enum Status { Active }
enum Status { Inactive }
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
        _assert_error("""
enum Status {
    Active
    Inactive
    Active
}
""", "Duplicate value 'Active' in enum 'Status'")

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
enum A { X X Y }
enum B { X Y Z }
""")
        messages = _messages(errors)
        assert any("in enum 'A'" in m for m in messages)
        assert not any("in enum 'B'" in m for m in messages)

    def test_triple_duplicate_reports_once(self) -> None:
        errors = _analyze("""
enum Foo { A A A }
""")
        messages = _messages(errors)
        assert messages.count("Duplicate value 'A' in enum 'Foo'") == 1


# ###############
# Duplicate Field Names
# ###############


class TestDuplicateFieldNames:
    def test_duplicate_field_in_type(self) -> None:
        _assert_error("""
type Address {
    field street: String
    field city: String
    field street: String
}
""", "Duplicate field name 'street' in type 'Address'")

    def test_duplicate_field_in_interface(self) -> None:
        _assert_error("""
interface OrderRequest {
    field order_id: String
    field order_id: Int
}
""", "Duplicate field name 'order_id' in interface 'OrderRequest'")

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
        _assert_error("""
type Order {
    field status: OrderStatus
}
""", "Undefined type 'OrderStatus'")

    def test_undefined_named_type_in_interface_field(self) -> None:
        _assert_error("""
interface Request {
    field item: OrderItem
}
""", "Undefined type 'OrderItem'")

    def test_enum_used_as_field_type_ok(self) -> None:
        _assert_clean("""
enum Status { Active }
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
        _assert_error("""
interface Batch {
    field items: List<UnknownItem>
}
""", "Undefined type 'UnknownItem'")

    def test_undefined_key_in_map(self) -> None:
        _assert_error("""
interface Catalog {
    field entries: Map<BadKey, String>
}
""", "Undefined type 'BadKey'")

    def test_undefined_value_in_map(self) -> None:
        _assert_error("""
interface Catalog {
    field entries: Map<String, BadValue>
}
""", "Undefined type 'BadValue'")

    def test_undefined_type_in_optional(self) -> None:
        _assert_error("""
interface Response {
    field meta: Optional<UnknownMeta>
}
""", "Undefined type 'UnknownMeta'")

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
        _assert_error("""
component Foo {
    requires UnknownInterface
}
""", "refers to unknown interface 'UnknownInterface'")

    def test_undefined_interface_in_provides(self) -> None:
        _assert_error("""
component Foo {
    provides UnknownInterface
}
""", "refers to unknown interface 'UnknownInterface'")

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
        _assert_error("""
interface OrderRequest @v2 { field id: String }
component OrderService {
    requires OrderRequest @v1
}
""", "no version 'v1' of interface 'OrderRequest' is defined")

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
        _assert_error("""
interface OrderRequest { field id: String }
component OrderService {
    requires OrderRequest @v1
}
""", "no version 'v1' of interface 'OrderRequest' is defined")

    def test_system_with_undefined_requires(self) -> None:
        _assert_error("""
system Foo {
    requires MissingInterface
}
""", "refers to unknown interface 'MissingInterface'")

    def test_system_with_undefined_provides(self) -> None:
        _assert_error("""
system Foo {
    provides MissingInterface
}
""", "refers to unknown interface 'MissingInterface'")


# ###############
# Connection Endpoint Validation
# ###############


class TestConnectionEndpoints:
    def test_unknown_source_in_component_connection(self) -> None:
        _assert_error("""
interface Signal { field v: Bool }
component Router {
    component Output { requires Signal }
    connect UnknownInput -> Output by Signal
}
""", "connection source 'UnknownInput' is not a known member entity")

    def test_unknown_target_in_component_connection(self) -> None:
        _assert_error("""
interface Signal { field v: Bool }
component Router {
    component Input { provides Signal }
    connect Input -> UnknownOutput by Signal
}
""", "connection target 'UnknownOutput' is not a known member entity")

    def test_unknown_source_in_system_connection(self) -> None:
        _assert_error("""
interface DataFeed { field payload: String }
system Pipeline {
    component Consumer { requires DataFeed }
    connect MissingProducer -> Consumer by DataFeed
}
""", "connection source 'MissingProducer' is not a known member entity")

    def test_unknown_target_in_system_connection(self) -> None:
        _assert_error("""
interface DataFeed { field payload: String }
system Pipeline {
    component Producer { provides DataFeed }
    connect Producer -> MissingConsumer by DataFeed
}
""", "connection target 'MissingConsumer' is not a known member entity")

    def test_valid_system_connection(self) -> None:
        _assert_clean("""
interface DataFeed { field payload: String }
system Pipeline {
    component Producer { provides DataFeed }
    component Consumer { requires DataFeed }
    connect Producer -> Consumer by DataFeed
}
""")

    def test_valid_component_connection(self) -> None:
        _assert_clean("""
interface Signal { field value: Int }
component Processor {
    component Source { provides Signal }
    component Sink { requires Signal }
    connect Source -> Sink by Signal
}
""")

    def test_connection_with_undefined_interface(self) -> None:
        _assert_error("""
system Pipeline {
    component A {}
    component B {}
    connect A -> B by UndefinedInterface
}
""", "refers to unknown interface 'UndefinedInterface'")

    def test_connection_with_versioned_interface_ok(self) -> None:
        _assert_clean("""
interface Feed @v1 { field data: String }
system Pipeline {
    component A { provides Feed @v1 }
    component B { requires Feed @v1 }
    connect A -> B by Feed @v1
}
""")

    def test_connection_endpoint_can_be_sub_system(self) -> None:
        _assert_clean("""
interface API { field endpoint: String }
system Enterprise {
    system Frontend { provides API }
    system Backend { requires API }
    connect Frontend -> Backend by API
}
""")

    def test_external_component_valid_connection_endpoint(self) -> None:
        _assert_clean("""
interface PayReq { field amount: Decimal }
system ECommerce {
    component OrderService { provides PayReq }
    external component StripeAPI { requires PayReq }
    connect OrderService -> StripeAPI by PayReq
}
""")


# ###############
# Duplicate Nested Names
# ###############


class TestDuplicateNestedNames:
    def test_duplicate_sub_component_in_component(self) -> None:
        _assert_error("""
component Router {
    component Leg {}
    component Leg {}
}
""", "Duplicate sub-component name 'Leg'")

    def test_duplicate_component_in_system(self) -> None:
        _assert_error("""
system Platform {
    component Worker {}
    component Worker {}
}
""", "Duplicate component name 'Worker'")

    def test_duplicate_sub_system_in_system(self) -> None:
        _assert_error("""
system Enterprise {
    system Division {}
    system Division {}
}
""", "Duplicate sub-system name 'Division'")

    def test_component_and_system_same_name_in_system(self) -> None:
        _assert_error("""
system Enterprise {
    component Foo {}
    system Foo {}
}
""", "name 'Foo' is used for both a component and a sub-system")

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
        source_file = parse("enum Status { Active Inactive }")
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

    def test_connection_with_known_interface_model(self) -> None:
        arch_file = ArchFile(
            interfaces=[InterfaceDef(name="Signal", version=None)],
            systems=[
                System(
                    name="Sys",
                    components=[
                        Component(name="A"),
                        Component(name="B"),
                    ],
                    connections=[
                        Connection(
                            source=ConnectionEndpoint(entity="A"),
                            target=ConnectionEndpoint(entity="B"),
                            interface=InterfaceRef(name="Signal"),
                        )
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
                        Field(name="items", type=ListTypeRef(element_type=NamedTypeRef(name="Item")))
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
                    fields=[
                        Field(name="items", type=NamedTypeRef(name="UnknownType"))
                    ],
                )
            ],
        )
        errors = analyze(arch_file)
        assert any("Undefined type 'UnknownType'" in e.message for e in errors)
