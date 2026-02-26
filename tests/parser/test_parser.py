# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ArchML recursive-descent parser."""

import pytest

from archml.model.entities import (
    ArchFile,
    ConnectionEndpoint,
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
)
from archml.parser.parser import ParseError, parse

# ###############
# Test Helpers
# ###############


def _parse(source: str) -> ArchFile:
    """Parse a source string and return the ArchFile model."""
    return parse(source)


# ###############
# Empty Input
# ###############


class TestEmptyInput:
    def test_empty_string_returns_empty_arch_file(self) -> None:
        result = _parse("")
        assert isinstance(result, ArchFile)
        assert result.imports == []
        assert result.enums == []
        assert result.types == []
        assert result.interfaces == []
        assert result.components == []
        assert result.systems == []

    def test_whitespace_only_returns_empty_arch_file(self) -> None:
        result = _parse("   \t\n\n  ")
        assert result.imports == []
        assert result.components == []

    def test_comment_only_returns_empty_arch_file(self) -> None:
        result = _parse("// just a comment\n/* block too */")
        assert result.imports == []


# ###############
# Import Declarations
# ###############


class TestImportDeclarations:
    def test_simple_import(self) -> None:
        result = _parse("from interfaces/order import OrderRequest")
        assert len(result.imports) == 1
        imp = result.imports[0]
        assert imp.source_path == "interfaces/order"
        assert imp.entities == ["OrderRequest"]

    def test_import_single_segment_path(self) -> None:
        result = _parse("from types import OrderItem")
        assert result.imports[0].source_path == "types"

    def test_import_multi_segment_path(self) -> None:
        result = _parse("from dir/sub/file import Entity")
        assert result.imports[0].source_path == "dir/sub/file"

    def test_import_multiple_entities(self) -> None:
        result = _parse("from interfaces/order import OrderRequest, OrderConfirmation")
        imp = result.imports[0]
        assert imp.entities == ["OrderRequest", "OrderConfirmation"]

    def test_import_three_entities(self) -> None:
        result = _parse(
            "from interfaces/order import"
            " OrderRequest, OrderConfirmation, PaymentRequest"
        )
        assert result.imports[0].entities == [
            "OrderRequest",
            "OrderConfirmation",
            "PaymentRequest",
        ]

    def test_cross_repo_import(self) -> None:
        result = _parse("from @payments/services/payment import PaymentService")
        imp = result.imports[0]
        assert imp.source_path == "@payments/services/payment"
        assert imp.entities == ["PaymentService"]

    def test_cross_repo_import_single_segment(self) -> None:
        result = _parse("from @repo/module import Entity")
        assert result.imports[0].source_path == "@repo/module"

    def test_multiple_imports(self) -> None:
        source = """\
from interfaces/order import OrderRequest, OrderConfirmation
from components/order_service import OrderService
"""
        result = _parse(source)
        assert len(result.imports) == 2
        assert result.imports[0].source_path == "interfaces/order"
        assert result.imports[1].source_path == "components/order_service"

    def test_import_entities_are_identifiers(self) -> None:
        result = _parse("from types import OrderItem, OrderStatus")
        assert result.imports[0].entities == ["OrderItem", "OrderStatus"]


# ###############
# Enum Declarations
# ###############


class TestEnumDeclarations:
    def test_empty_enum(self) -> None:
        result = _parse("enum Empty {}")
        assert len(result.enums) == 1
        enum = result.enums[0]
        assert enum.name == "Empty"
        assert enum.values == []

    def test_enum_with_single_value(self) -> None:
        result = _parse("enum Status { Active }")
        assert result.enums[0].values == ["Active"]

    def test_enum_with_multiple_values(self) -> None:
        source = """\
enum OrderStatus {
    Pending
    Confirmed
    Shipped
    Delivered
    Cancelled
}"""
        result = _parse(source)
        enum = result.enums[0]
        assert enum.name == "OrderStatus"
        assert enum.values == [
            "Pending",
            "Confirmed",
            "Shipped",
            "Delivered",
            "Cancelled",
        ]

    def test_enum_with_title(self) -> None:
        source = """\
enum Status {
    title = "Order Status"
    Active
}"""
        result = _parse(source)
        enum = result.enums[0]
        assert enum.title == "Order Status"
        assert enum.values == ["Active"]

    def test_enum_with_description(self) -> None:
        source = """\
enum Status {
    description = "Current state of an order."
    Pending
}"""
        result = _parse(source)
        assert result.enums[0].description == "Current state of an order."

    def test_enum_with_tags(self) -> None:
        source = """\
enum Status {
    tags = ["domain", "order"]
    Pending
}"""
        result = _parse(source)
        assert result.enums[0].tags == ["domain", "order"]

    def test_enum_with_all_attributes(self) -> None:
        source = """\
enum OrderStatus {
    title = "Order Status"
    description = "Status of a customer order."
    tags = ["core"]
    Pending
    Confirmed
}"""
        result = _parse(source)
        enum = result.enums[0]
        assert enum.name == "OrderStatus"
        assert enum.title == "Order Status"
        assert enum.description == "Status of a customer order."
        assert enum.tags == ["core"]
        assert enum.values == ["Pending", "Confirmed"]

    def test_enum_title_default_is_none(self) -> None:
        result = _parse("enum Status { Active }")
        assert result.enums[0].title is None

    def test_enum_description_default_is_none(self) -> None:
        result = _parse("enum Status { Active }")
        assert result.enums[0].description is None

    def test_enum_tags_default_is_empty(self) -> None:
        result = _parse("enum Status { Active }")
        assert result.enums[0].tags == []

    def test_multiple_enums(self) -> None:
        source = "enum A { X }\nenum B { Y }"
        result = _parse(source)
        assert len(result.enums) == 2
        assert result.enums[0].name == "A"
        assert result.enums[1].name == "B"


# ###############
# Type Declarations
# ###############


class TestTypeDeclarations:
    def test_empty_type(self) -> None:
        result = _parse("type Empty {}")
        assert len(result.types) == 1
        assert result.types[0].name == "Empty"
        assert result.types[0].fields == []

    def test_type_with_single_primitive_field(self) -> None:
        result = _parse("type Order { field order_id: String }")
        t = result.types[0]
        assert len(t.fields) == 1
        assert t.fields[0].name == "order_id"
        assert isinstance(t.fields[0].type, PrimitiveTypeRef)
        assert t.fields[0].type.primitive == PrimitiveType.STRING

    def test_type_with_multiple_fields(self) -> None:
        source = """\
type OrderItem {
    field product_id: String
    field quantity: Int
    field unit_price: Decimal
}"""
        result = _parse(source)
        t = result.types[0]
        assert t.name == "OrderItem"
        assert len(t.fields) == 3
        assert t.fields[0].name == "product_id"
        assert t.fields[1].name == "quantity"
        assert t.fields[2].name == "unit_price"

    def test_type_with_title(self) -> None:
        source = 'type Order {\n    title = "Order Data"\n    field id: String\n}'
        result = _parse(source)
        assert result.types[0].title == "Order Data"

    def test_type_with_description(self) -> None:
        source = """\
type Order {
    description = "Represents an order."
    field id: String
}"""
        result = _parse(source)
        assert result.types[0].description == "Represents an order."

    def test_type_with_tags(self) -> None:
        source = 'type Order {\n    tags = ["domain"]\n    field id: String\n}'
        result = _parse(source)
        assert result.types[0].tags == ["domain"]

    def test_type_with_named_type_field(self) -> None:
        result = _parse("type Order { field item: OrderItem }")
        assert isinstance(result.types[0].fields[0].type, NamedTypeRef)
        assert result.types[0].fields[0].type.name == "OrderItem"

    def test_type_with_list_field(self) -> None:
        result = _parse("type Order { field items: List<OrderItem> }")
        field = result.types[0].fields[0]
        assert isinstance(field.type, ListTypeRef)
        assert isinstance(field.type.element_type, NamedTypeRef)

    def test_type_with_map_field(self) -> None:
        result = _parse("type Store { field index: Map<String, Int> }")
        field = result.types[0].fields[0]
        assert isinstance(field.type, MapTypeRef)

    def test_type_with_optional_field(self) -> None:
        result = _parse("type Order { field note: Optional<String> }")
        field = result.types[0].fields[0]
        assert isinstance(field.type, OptionalTypeRef)

    def test_multiple_types(self) -> None:
        source = "type A { field x: String }\ntype B { field y: Int }"
        result = _parse(source)
        assert len(result.types) == 2
        assert result.types[0].name == "A"
        assert result.types[1].name == "B"


# ###############
# Interface Declarations
# ###############


class TestInterfaceDeclarations:
    def test_empty_interface(self) -> None:
        result = _parse("interface Empty {}")
        assert len(result.interfaces) == 1
        iface = result.interfaces[0]
        assert iface.name == "Empty"
        assert iface.version is None
        assert iface.fields == []

    def test_interface_with_version(self) -> None:
        result = _parse("interface OrderRequest @v2 {}")
        iface = result.interfaces[0]
        assert iface.name == "OrderRequest"
        assert iface.version == "v2"

    def test_interface_version_v1(self) -> None:
        result = _parse("interface OrderRequest @v1 {}")
        assert result.interfaces[0].version == "v1"

    def test_interface_without_version(self) -> None:
        result = _parse("interface OrderRequest {}")
        assert result.interfaces[0].version is None

    def test_interface_with_title(self) -> None:
        source = 'interface OrderRequest {\n    title = "Order Creation Request"\n}'
        result = _parse(source)
        assert result.interfaces[0].title == "Order Creation Request"

    def test_interface_with_description(self) -> None:
        source = """\
interface OrderRequest {
    description = "Payload for submitting a new customer order."
}"""
        result = _parse(source)
        desc = result.interfaces[0].description
        assert desc == "Payload for submitting a new customer order."

    def test_interface_with_tags(self) -> None:
        source = 'interface OrderRequest {\n    tags = ["api", "order"]\n}'
        result = _parse(source)
        assert result.interfaces[0].tags == ["api", "order"]

    def test_interface_with_fields(self) -> None:
        source = """\
interface OrderRequest {
    field order_id: String
    field customer_id: String
    field items: List<OrderItem>
    field total_amount: Decimal
}"""
        result = _parse(source)
        iface = result.interfaces[0]
        assert len(iface.fields) == 4
        assert iface.fields[0].name == "order_id"
        assert isinstance(iface.fields[0].type, PrimitiveTypeRef)
        assert iface.fields[2].name == "items"
        assert isinstance(iface.fields[2].type, ListTypeRef)

    def test_interface_field_with_description(self) -> None:
        source = """\
interface OrderRequest {
    field total_amount: Decimal {
        description = "Grand total including tax and shipping."
    }
}"""
        result = _parse(source)
        field = result.interfaces[0].fields[0]
        assert field.name == "total_amount"
        assert field.description == "Grand total including tax and shipping."

    def test_interface_field_with_schema(self) -> None:
        source = """\
interface OrderRequest {
    field currency: String {
        description = "ISO 4217 currency code."
        schema = "Three-letter uppercase code, e.g. USD, EUR."
    }
}"""
        result = _parse(source)
        field = result.interfaces[0].fields[0]
        assert field.description == "ISO 4217 currency code."
        assert field.schema == "Three-letter uppercase code, e.g. USD, EUR."

    def test_interface_with_all_attributes(self) -> None:
        source = """\
interface OrderRequest {
    title = "Order Creation Request"
    description = "Payload for submitting a new customer order."
    tags = ["api"]
    field order_id: String
}"""
        result = _parse(source)
        iface = result.interfaces[0]
        assert iface.title == "Order Creation Request"
        assert iface.description == "Payload for submitting a new customer order."
        assert iface.tags == ["api"]
        assert len(iface.fields) == 1

    def test_versioned_interface_with_fields(self) -> None:
        source = """\
interface OrderRequest @v2 {
    field order_id: String
    field customer_id: String
    field shipping_method: String
}"""
        result = _parse(source)
        iface = result.interfaces[0]
        assert iface.version == "v2"
        assert len(iface.fields) == 3

    def test_multiple_interfaces(self) -> None:
        source = "interface A {}\ninterface B {}"
        result = _parse(source)
        assert len(result.interfaces) == 2
        assert result.interfaces[0].name == "A"
        assert result.interfaces[1].name == "B"


# ###############
# Field Type References
# ###############


class TestFieldTypeReferences:
    def _parse_field_type(self, type_str: str) -> Field:
        """Helper: parse a single field declaration inside a type."""
        result = _parse(f"type T {{ field x: {type_str} }}")
        return result.types[0].fields[0]

    def test_primitive_string(self) -> None:
        f = self._parse_field_type("String")
        assert isinstance(f.type, PrimitiveTypeRef)
        assert f.type.primitive == PrimitiveType.STRING

    def test_primitive_int(self) -> None:
        f = self._parse_field_type("Int")
        assert f.type == PrimitiveTypeRef(PrimitiveType.INT)

    def test_primitive_float(self) -> None:
        f = self._parse_field_type("Float")
        assert f.type == PrimitiveTypeRef(PrimitiveType.FLOAT)

    def test_primitive_decimal(self) -> None:
        f = self._parse_field_type("Decimal")
        assert f.type == PrimitiveTypeRef(PrimitiveType.DECIMAL)

    def test_primitive_bool(self) -> None:
        f = self._parse_field_type("Bool")
        assert f.type == PrimitiveTypeRef(PrimitiveType.BOOL)

    def test_primitive_bytes(self) -> None:
        f = self._parse_field_type("Bytes")
        assert f.type == PrimitiveTypeRef(PrimitiveType.BYTES)

    def test_primitive_timestamp(self) -> None:
        f = self._parse_field_type("Timestamp")
        assert f.type == PrimitiveTypeRef(PrimitiveType.TIMESTAMP)

    def test_primitive_datetime(self) -> None:
        f = self._parse_field_type("Datetime")
        assert f.type == PrimitiveTypeRef(PrimitiveType.DATETIME)

    def test_file_type(self) -> None:
        f = self._parse_field_type("File")
        assert isinstance(f.type, FileTypeRef)

    def test_directory_type(self) -> None:
        f = self._parse_field_type("Directory")
        assert isinstance(f.type, DirectoryTypeRef)

    def test_list_of_primitive(self) -> None:
        f = self._parse_field_type("List<String>")
        assert isinstance(f.type, ListTypeRef)
        assert isinstance(f.type.element_type, PrimitiveTypeRef)
        assert f.type.element_type.primitive == PrimitiveType.STRING

    def test_list_of_named_type(self) -> None:
        f = self._parse_field_type("List<OrderItem>")
        assert isinstance(f.type, ListTypeRef)
        assert isinstance(f.type.element_type, NamedTypeRef)
        assert f.type.element_type.name == "OrderItem"

    def test_map_of_string_to_int(self) -> None:
        f = self._parse_field_type("Map<String, Int>")
        assert isinstance(f.type, MapTypeRef)
        assert isinstance(f.type.key_type, PrimitiveTypeRef)
        assert f.type.key_type.primitive == PrimitiveType.STRING
        assert isinstance(f.type.value_type, PrimitiveTypeRef)
        assert f.type.value_type.primitive == PrimitiveType.INT

    def test_map_of_string_to_named(self) -> None:
        f = self._parse_field_type("Map<String, OrderItem>")
        assert isinstance(f.type, MapTypeRef)
        assert isinstance(f.type.value_type, NamedTypeRef)

    def test_optional_of_string(self) -> None:
        f = self._parse_field_type("Optional<String>")
        assert isinstance(f.type, OptionalTypeRef)
        assert isinstance(f.type.inner_type, PrimitiveTypeRef)

    def test_optional_of_named(self) -> None:
        f = self._parse_field_type("Optional<TransactionId>")
        assert isinstance(f.type, OptionalTypeRef)
        assert isinstance(f.type.inner_type, NamedTypeRef)
        assert f.type.inner_type.name == "TransactionId"

    def test_named_type_reference(self) -> None:
        f = self._parse_field_type("OrderItem")
        assert isinstance(f.type, NamedTypeRef)
        assert f.type.name == "OrderItem"

    def test_nested_list_in_map(self) -> None:
        f = self._parse_field_type("Map<String, List<Int>>")
        assert isinstance(f.type, MapTypeRef)
        assert isinstance(f.type.value_type, ListTypeRef)

    def test_nested_optional_in_list(self) -> None:
        f = self._parse_field_type("List<Optional<String>>")
        assert isinstance(f.type, ListTypeRef)
        assert isinstance(f.type.element_type, OptionalTypeRef)

    def test_deeply_nested_type(self) -> None:
        f = self._parse_field_type("Optional<List<Map<String, Int>>>")
        assert isinstance(f.type, OptionalTypeRef)
        assert isinstance(f.type.inner_type, ListTypeRef)
        assert isinstance(f.type.inner_type.element_type, MapTypeRef)


# ###############
# Field Annotations
# ###############


class TestFieldAnnotations:
    def _parse_field(self, field_source: str) -> Field:
        result = _parse(f"type T {{ {field_source} }}")
        return result.types[0].fields[0]

    def test_field_without_annotation_has_no_description(self) -> None:
        f = self._parse_field("field x: String")
        assert f.description is None

    def test_field_without_annotation_has_no_schema(self) -> None:
        f = self._parse_field("field x: String")
        assert f.schema is None

    def test_field_without_annotation_has_no_filetype(self) -> None:
        f = self._parse_field("field x: String")
        assert f.filetype is None

    def test_field_with_description(self) -> None:
        f = self._parse_field('field amount: Decimal { description = "Grand total." }')
        assert f.description == "Grand total."

    def test_field_with_schema(self) -> None:
        source = 'field code: String { schema = "Three-letter ISO code." }'
        f = self._parse_field(source)
        assert f.schema == "Three-letter ISO code."

    def test_field_with_filetype(self) -> None:
        f = self._parse_field('field report: File { filetype = "PDF" }')
        assert f.filetype == "PDF"
        assert isinstance(f.type, FileTypeRef)

    def test_field_with_description_and_schema(self) -> None:
        source = (
            "field currency: String"
            ' { description = "Currency code." schema = "e.g. USD." }'
        )
        f = self._parse_field(source)
        assert f.description == "Currency code."
        assert f.schema == "e.g. USD."

    def test_file_field_with_filetype_and_schema(self) -> None:
        source = (
            "field config: File"
            ' { filetype = "YAML" schema = "Top-level keys: server." }'
        )
        f = self._parse_field(source)
        assert isinstance(f.type, FileTypeRef)
        assert f.filetype == "YAML"
        assert f.schema == "Top-level keys: server."

    def test_directory_field_with_schema(self) -> None:
        source = 'field artifact: Directory { schema = "Contains manifests/*.yaml" }'
        f = self._parse_field(source)
        assert isinstance(f.type, DirectoryTypeRef)
        assert f.schema == "Contains manifests/*.yaml"

    def test_all_field_annotations(self) -> None:
        source = (
            "field report: File"
            ' { filetype = "PDF" schema = "Monthly report."'
            ' description = "Report file." }'
        )
        f = self._parse_field(source)
        assert f.filetype == "PDF"
        assert f.schema == "Monthly report."
        assert f.description == "Report file."


# ###############
# Component Declarations
# ###############


class TestComponentDeclarations:
    def test_empty_component(self) -> None:
        result = _parse("component Empty {}")
        assert len(result.components) == 1
        comp = result.components[0]
        assert comp.name == "Empty"
        assert comp.is_external is False
        assert comp.requires == []
        assert comp.provides == []
        assert comp.components == []
        assert comp.connections == []

    def test_component_with_title(self) -> None:
        result = _parse('component OrderService { title = "Order Service" }')
        assert result.components[0].title == "Order Service"

    def test_component_with_description(self) -> None:
        result = _parse('component OrderService { description = "Accepts orders." }')
        assert result.components[0].description == "Accepts orders."

    def test_component_with_tags(self) -> None:
        result = _parse('component GW { tags = ["critical", "pci-scope"] }')
        assert result.components[0].tags == ["critical", "pci-scope"]

    def test_component_with_requires(self) -> None:
        result = _parse("component X { requires OrderRequest }")
        comp = result.components[0]
        assert len(comp.requires) == 1
        assert comp.requires[0].name == "OrderRequest"
        assert comp.requires[0].version is None

    def test_component_with_multiple_requires(self) -> None:
        source = """\
component X {
    requires PaymentRequest
    requires InventoryCheck
    requires OrderRequest
}"""
        result = _parse(source)
        comp = result.components[0]
        assert len(comp.requires) == 3
        assert [r.name for r in comp.requires] == [
            "PaymentRequest",
            "InventoryCheck",
            "OrderRequest",
        ]

    def test_component_with_provides(self) -> None:
        result = _parse("component X { provides OrderConfirmation }")
        comp = result.components[0]
        assert len(comp.provides) == 1
        assert comp.provides[0].name == "OrderConfirmation"

    def test_component_with_versioned_requires(self) -> None:
        result = _parse("component X { requires OrderRequest @v2 }")
        ref = result.components[0].requires[0]
        assert ref.name == "OrderRequest"
        assert ref.version == "v2"

    def test_component_with_versioned_provides(self) -> None:
        result = _parse("component X { provides OrderConfirmation @v1 }")
        ref = result.components[0].provides[0]
        assert ref.name == "OrderConfirmation"
        assert ref.version == "v1"

    def test_component_with_requires_and_provides(self) -> None:
        source = """\
component OrderService {
    title = "Order Service"
    description = "Accepts, validates, and processes customer orders."
    requires OrderRequest
    requires PaymentRequest
    requires InventoryCheck
    provides OrderConfirmation
}"""
        result = _parse(source)
        comp = result.components[0]
        assert comp.name == "OrderService"
        assert comp.title == "Order Service"
        assert len(comp.requires) == 3
        assert len(comp.provides) == 1

    def test_nested_component(self) -> None:
        source = """\
component OrderService {
    component Validator {
        requires OrderRequest
        provides ValidationResult
    }
}"""
        result = _parse(source)
        outer = result.components[0]
        assert len(outer.components) == 1
        inner = outer.components[0]
        assert inner.name == "Validator"
        assert inner.requires[0].name == "OrderRequest"

    def test_deeply_nested_components(self) -> None:
        source = """\
component A {
    component B {
        component C {
            requires X
        }
    }
}"""
        result = _parse(source)
        a = result.components[0]
        b = a.components[0]
        c = b.components[0]
        assert c.name == "C"
        assert c.requires[0].name == "X"

    def test_component_with_connection(self) -> None:
        source = """\
component OrderService {
    component Validator { provides ValidationResult }
    component Processor { requires ValidationResult }
    connect Validator -> Processor by ValidationResult
}"""
        result = _parse(source)
        comp = result.components[0]
        assert len(comp.connections) == 1
        conn = comp.connections[0]
        assert conn.source.entity == "Validator"
        assert conn.target.entity == "Processor"
        assert conn.interface.name == "ValidationResult"

    def test_external_component(self) -> None:
        result = _parse("external component StripeSDK { requires PaymentRequest }")
        comp = result.components[0]
        assert comp.is_external is True
        assert comp.name == "StripeSDK"

    def test_component_defaults(self) -> None:
        result = _parse("component X {}")
        comp = result.components[0]
        assert comp.title is None
        assert comp.description is None
        assert comp.tags == []
        assert comp.is_external is False

    def test_multiple_top_level_components(self) -> None:
        source = "component A {}\ncomponent B {}\ncomponent C {}"
        result = _parse(source)
        assert len(result.components) == 3
        assert [c.name for c in result.components] == ["A", "B", "C"]


# ###############
# System Declarations
# ###############


class TestSystemDeclarations:
    def test_empty_system(self) -> None:
        result = _parse("system Empty {}")
        assert len(result.systems) == 1
        system = result.systems[0]
        assert system.name == "Empty"
        assert system.is_external is False
        assert system.components == []
        assert system.systems == []
        assert system.connections == []

    def test_system_with_title(self) -> None:
        result = _parse('system ECommerce { title = "E-Commerce Platform" }')
        assert result.systems[0].title == "E-Commerce Platform"

    def test_system_with_description(self) -> None:
        result = _parse('system ECommerce { description = "Customer-facing store." }')
        assert result.systems[0].description == "Customer-facing store."

    def test_system_with_tags(self) -> None:
        result = _parse('system ECommerce { tags = ["platform", "core"] }')
        assert result.systems[0].tags == ["platform", "core"]

    def test_system_with_inline_component(self) -> None:
        source = """\
system ECommerce {
    component OrderService {
        requires OrderRequest
        provides OrderConfirmation
    }
}"""
        result = _parse(source)
        system = result.systems[0]
        assert len(system.components) == 1
        assert system.components[0].name == "OrderService"

    def test_system_with_multiple_components(self) -> None:
        source = """\
system ECommerce {
    component OrderService {}
    component PaymentGateway {}
    component InventoryManager {}
}"""
        result = _parse(source)
        system = result.systems[0]
        assert len(system.components) == 3
        assert [c.name for c in system.components] == [
            "OrderService",
            "PaymentGateway",
            "InventoryManager",
        ]

    def test_system_with_connection(self) -> None:
        source = """\
system ECommerce {
    component A {}
    component B {}
    connect A -> B by Interface
}"""
        result = _parse(source)
        system = result.systems[0]
        assert len(system.connections) == 1
        conn = system.connections[0]
        assert conn.source.entity == "A"
        assert conn.target.entity == "B"
        assert conn.interface.name == "Interface"

    def test_system_with_multiple_connections(self) -> None:
        source = """\
system ECommerce {
    connect OrderService -> PaymentGateway by PaymentRequest
    connect OrderService -> InventoryManager by InventoryCheck
}"""
        result = _parse(source)
        assert len(result.systems[0].connections) == 2

    def test_system_with_nested_system(self) -> None:
        source = """\
system Enterprise {
    system ECommerce {}
    system Warehouse {}
}"""
        result = _parse(source)
        system = result.systems[0]
        assert len(system.systems) == 2
        assert system.systems[0].name == "ECommerce"
        assert system.systems[1].name == "Warehouse"

    def test_system_with_use_component(self) -> None:
        source = """\
system ECommerce {
    use component OrderService
}"""
        result = _parse(source)
        system = result.systems[0]
        assert len(system.components) == 1
        assert system.components[0].name == "OrderService"

    def test_system_with_use_system(self) -> None:
        source = """\
system Enterprise {
    use system ECommerce
}"""
        result = _parse(source)
        system = result.systems[0]
        assert len(system.systems) == 1
        assert system.systems[0].name == "ECommerce"

    def test_system_with_multiple_use_statements(self) -> None:
        source = """\
system ECommerce {
    use component OrderService
    use component PaymentGateway
    use component InventoryManager
}"""
        result = _parse(source)
        system = result.systems[0]
        assert len(system.components) == 3
        assert [c.name for c in system.components] == [
            "OrderService",
            "PaymentGateway",
            "InventoryManager",
        ]

    def test_system_with_mixed_use_and_inline(self) -> None:
        source = """\
system ECommerce {
    use component OrderService
    component PaymentGateway {
        requires PaymentRequest
        provides PaymentResult
    }
}"""
        result = _parse(source)
        system = result.systems[0]
        assert len(system.components) == 2
        assert system.components[0].name == "OrderService"
        assert system.components[1].name == "PaymentGateway"

    def test_external_system(self) -> None:
        result = _parse("external system StripeAPI { requires PaymentRequest }")
        system = result.systems[0]
        assert system.is_external is True
        assert system.name == "StripeAPI"

    def test_external_system_with_title(self) -> None:
        source = """\
external system StripeAPI {
    title = "Stripe Payment API"
}"""
        result = _parse(source)
        system = result.systems[0]
        assert system.is_external is True
        assert system.title == "Stripe Payment API"
        assert system.components == []

    def test_system_defaults(self) -> None:
        result = _parse("system X {}")
        system = result.systems[0]
        assert system.title is None
        assert system.description is None
        assert system.tags == []
        assert system.is_external is False

    def test_nested_system_with_connections(self) -> None:
        source = """\
system Enterprise {
    title = "Enterprise Landscape"
    system ECommerce {}
    system Warehouse {}
    connect ECommerce -> Warehouse by InventorySync
}"""
        result = _parse(source)
        system = result.systems[0]
        assert system.title == "Enterprise Landscape"
        assert len(system.systems) == 2
        assert len(system.connections) == 1
        assert system.connections[0].interface.name == "InventorySync"


# ###############
# Connection Declarations
# ###############


class TestConnectionDeclarations:
    def test_simple_connection(self) -> None:
        result = _parse("""\
system S {
    connect A -> B by Interface
}""")
        conn = result.systems[0].connections[0]
        assert conn.source.entity == "A"
        assert conn.target.entity == "B"
        assert conn.interface.name == "Interface"
        assert conn.interface.version is None
        assert conn.protocol is None
        assert conn.is_async is False
        assert conn.description is None

    def test_connection_with_versioned_interface(self) -> None:
        result = _parse("system S { connect A -> B by Interface @v2 }")
        conn = result.systems[0].connections[0]
        assert conn.interface.name == "Interface"
        assert conn.interface.version == "v2"

    def test_connection_with_protocol(self) -> None:
        source = """\
system S {
    connect A -> B by Interface {
        protocol = "gRPC"
    }
}"""
        result = _parse(source)
        conn = result.systems[0].connections[0]
        assert conn.protocol == "gRPC"

    def test_connection_with_async_true(self) -> None:
        source = """\
system S {
    connect A -> B by Interface {
        async = true
    }
}"""
        result = _parse(source)
        assert result.systems[0].connections[0].is_async is True

    def test_connection_with_async_false(self) -> None:
        source = """\
system S {
    connect A -> B by Interface {
        async = false
    }
}"""
        result = _parse(source)
        assert result.systems[0].connections[0].is_async is False

    def test_connection_with_description(self) -> None:
        source = """\
system S {
    connect A -> B by Interface {
        description = "Initiates payment processing."
    }
}"""
        result = _parse(source)
        conn_desc = result.systems[0].connections[0].description
        assert conn_desc == "Initiates payment processing."

    def test_connection_with_all_annotations(self) -> None:
        source = """\
system S {
    connect OrderService -> PaymentGateway by PaymentRequest {
        protocol = "gRPC"
        async = true
        description = "Initiates payment processing for confirmed orders."
    }
}"""
        result = _parse(source)
        conn = result.systems[0].connections[0]
        assert conn.source.entity == "OrderService"
        assert conn.target.entity == "PaymentGateway"
        assert conn.interface.name == "PaymentRequest"
        assert conn.protocol == "gRPC"
        assert conn.is_async is True
        assert conn.description == "Initiates payment processing for confirmed orders."

    def test_connection_with_http_protocol(self) -> None:
        source = """\
system S {
    connect A -> B by Interface {
        protocol = "HTTP"
    }
}"""
        result = _parse(source)
        assert result.systems[0].connections[0].protocol == "HTTP"

    def test_multiple_connections_in_system(self) -> None:
        source = """\
system ECommerce {
    connect OrderService -> PaymentGateway by PaymentRequest
    connect OrderService -> InventoryManager by InventoryCheck
    connect PaymentGateway -> StripeAPI by PaymentRequest {
        protocol = "HTTP"
        async = true
    }
}"""
        result = _parse(source)
        conns = result.systems[0].connections
        assert len(conns) == 3
        assert conns[0].interface.name == "PaymentRequest"
        assert conns[1].interface.name == "InventoryCheck"
        assert conns[2].protocol == "HTTP"
        assert conns[2].is_async is True

    def test_connection_endpoint_entities(self) -> None:
        result = _parse(
            "system S { connect SourceService -> TargetService by MyInterface }"
        )
        conn = result.systems[0].connections[0]
        assert isinstance(conn.source, ConnectionEndpoint)
        assert isinstance(conn.target, ConnectionEndpoint)
        assert conn.source.entity == "SourceService"
        assert conn.target.entity == "TargetService"


# ###############
# Tags Parsing
# ###############


class TestTagsParsing:
    def test_empty_tags_list(self) -> None:
        result = _parse("component X { tags = [] }")
        assert result.components[0].tags == []

    def test_single_tag(self) -> None:
        result = _parse('component X { tags = ["critical"] }')
        assert result.components[0].tags == ["critical"]

    def test_multiple_tags(self) -> None:
        result = _parse('component X { tags = ["critical", "pci-scope", "core"] }')
        assert result.components[0].tags == ["critical", "pci-scope", "core"]

    def test_tags_with_hyphens(self) -> None:
        result = _parse('component X { tags = ["pci-scope", "high-availability"] }')
        assert "pci-scope" in result.components[0].tags

    def test_tags_on_system(self) -> None:
        result = _parse('system S { tags = ["platform"] }')
        assert result.systems[0].tags == ["platform"]

    def test_tags_on_enum(self) -> None:
        result = _parse('enum E { tags = ["domain"] Active }')
        assert result.enums[0].tags == ["domain"]

    def test_tags_on_type(self) -> None:
        result = _parse('type T { tags = ["data"] field x: String }')
        assert result.types[0].tags == ["data"]

    def test_tags_on_interface(self) -> None:
        result = _parse('interface I { tags = ["api"] }')
        assert result.interfaces[0].tags == ["api"]


# ###############
# Mixed Top-Level Declarations
# ###############


class TestMixedTopLevelDeclarations:
    def test_all_top_level_kinds_in_sequence(self) -> None:
        source = """\
from interfaces/order import OrderRequest
enum OrderStatus { Pending }
type OrderItem { field product_id: String }
interface OrderRequest { field order_id: String }
component OrderService { requires OrderRequest }
system ECommerce { use component OrderService }
"""
        result = _parse(source)
        assert len(result.imports) == 1
        assert len(result.enums) == 1
        assert len(result.types) == 1
        assert len(result.interfaces) == 1
        assert len(result.components) == 1
        assert len(result.systems) == 1

    def test_imports_before_declarations(self) -> None:
        source = """\
from types import OrderItem, OrderStatus
from interfaces/order import OrderRequest, OrderConfirmation

component OrderService {
    requires OrderRequest
    provides OrderConfirmation
}
"""
        result = _parse(source)
        assert len(result.imports) == 2
        assert len(result.components) == 1

    def test_multiple_systems_with_components(self) -> None:
        source = """\
system A {
    component X {}
    component Y {}
}
system B {
    component Z {}
}
"""
        result = _parse(source)
        assert len(result.systems) == 2
        assert len(result.systems[0].components) == 2
        assert len(result.systems[1].components) == 1


# ###############
# Full Language Examples
# ###############


class TestFullLanguageExamples:
    def test_complete_spec_example_types_file(self) -> None:
        """Parse the types.archml portion of the complete spec example."""
        source = """\
type OrderItem {
    field product_id: String
    field quantity: Int
    field unit_price: Decimal
}

enum OrderStatus {
    Pending
    Confirmed
    Shipped
    Delivered
    Cancelled
}

interface OrderRequest {
    field order_id: String
    field customer_id: String
    field items: List<OrderItem>
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

interface InventoryCheck {
    field product_id: String
    field quantity: Int
}

interface InventoryStatus {
    field product_id: String
    field available: Bool
}

interface ReportOutput {
    field report: File {
        filetype = "PDF"
        schema = "Monthly sales summary report."
    }
}
"""
        result = _parse(source)
        assert len(result.types) == 1
        assert len(result.enums) == 1
        assert len(result.interfaces) == 7

        # Verify OrderItem
        order_item = result.types[0]
        assert order_item.name == "OrderItem"
        assert len(order_item.fields) == 3

        # Verify OrderStatus enum
        status = result.enums[0]
        assert status.name == "OrderStatus"
        assert len(status.values) == 5
        assert "Shipped" in status.values

        # Verify OrderConfirmation interface uses named type and timestamp
        confirmation = next(
            i for i in result.interfaces if i.name == "OrderConfirmation"
        )
        assert confirmation.fields[1].name == "status"
        assert isinstance(confirmation.fields[1].type, NamedTypeRef)
        assert confirmation.fields[2].name == "confirmed_at"
        assert isinstance(confirmation.fields[2].type, PrimitiveTypeRef)
        assert confirmation.fields[2].type.primitive == PrimitiveType.TIMESTAMP

        # Verify PaymentResult with Optional
        payment_result = next(i for i in result.interfaces if i.name == "PaymentResult")
        txn_field = payment_result.fields[2]
        assert txn_field.name == "transaction_id"
        assert isinstance(txn_field.type, OptionalTypeRef)

        # Verify ReportOutput with File field
        report = next(i for i in result.interfaces if i.name == "ReportOutput")
        field = report.fields[0]
        assert isinstance(field.type, FileTypeRef)
        assert field.filetype == "PDF"
        assert "Monthly sales summary" in field.schema  # type: ignore[operator]

    def test_complete_spec_example_order_service_component(self) -> None:
        """Parse the components/order_service.archml portion."""
        import_line = (
            "from types import"
            " OrderItem, OrderRequest, PaymentRequest,"
            " InventoryCheck, OrderConfirmation"
        )
        source = f"""\
{import_line}

component OrderService {{
    title = "Order Service"
    description = "Accepts, validates, and processes customer orders."

    requires OrderRequest
    requires PaymentRequest
    requires InventoryCheck
    provides OrderConfirmation
}}
"""
        result = _parse(source)
        assert len(result.imports) == 1
        assert result.imports[0].entities == [
            "OrderItem",
            "OrderRequest",
            "PaymentRequest",
            "InventoryCheck",
            "OrderConfirmation",
        ]
        assert len(result.components) == 1
        comp = result.components[0]
        assert comp.name == "OrderService"
        assert comp.title == "Order Service"
        assert len(comp.requires) == 3
        assert len(comp.provides) == 1

    def test_complete_spec_example_ecommerce_system(self) -> None:
        """Parse the systems/ecommerce.archml portion."""
        source = """\
from types import PaymentRequest, PaymentResult, InventoryCheck, InventoryStatus
from components/order_service import OrderService

external system StripeAPI {
    title = "Stripe Payment API"
}

system ECommerce {
    title = "E-Commerce Platform"

    use component OrderService

    component PaymentGateway {
        title = "Payment Gateway"
        tags = ["critical", "pci-scope"]

        requires PaymentRequest
        provides PaymentResult
    }

    component InventoryManager {
        title = "Inventory Manager"

        requires InventoryCheck
        provides InventoryStatus
    }

    connect OrderService -> PaymentGateway by PaymentRequest
    connect OrderService -> InventoryManager by InventoryCheck {
        protocol = "HTTP"
    }
    connect PaymentGateway -> StripeAPI by PaymentRequest {
        protocol = "HTTP"
        async = true
    }
}
"""
        result = _parse(source)

        assert len(result.imports) == 2
        assert len(result.systems) == 2

        stripe = next(s for s in result.systems if s.name == "StripeAPI")
        assert stripe.is_external is True
        assert stripe.title == "Stripe Payment API"

        ecommerce = next(s for s in result.systems if s.name == "ECommerce")
        assert ecommerce.title == "E-Commerce Platform"
        assert len(ecommerce.components) == 3  # use + 2 inline

        gw = next(c for c in ecommerce.components if c.name == "PaymentGateway")
        assert gw.tags == ["critical", "pci-scope"]

        assert len(ecommerce.connections) == 3
        last_conn = ecommerce.connections[2]
        assert last_conn.protocol == "HTTP"
        assert last_conn.is_async is True

    def test_nested_component_with_connections(self) -> None:
        """Parse a component with nested sub-components and connections."""
        source = """\
component OrderService {
    title = "Order Service"

    component Validator {
        title = "Order Validator"

        requires OrderRequest
        provides ValidationResult
    }

    component Processor {
        title = "Order Processor"

        requires ValidationResult
        requires PaymentRequest
        requires InventoryCheck
        provides OrderConfirmation
    }

    connect Validator -> Processor by ValidationResult
}
"""
        result = _parse(source)
        comp = result.components[0]
        assert comp.name == "OrderService"
        assert len(comp.components) == 2
        assert len(comp.connections) == 1

        validator = comp.components[0]
        assert validator.name == "Validator"
        assert validator.requires[0].name == "OrderRequest"
        assert validator.provides[0].name == "ValidationResult"

        conn = comp.connections[0]
        assert conn.source.entity == "Validator"
        assert conn.target.entity == "Processor"
        assert conn.interface.name == "ValidationResult"

    def test_enterprise_nested_systems(self) -> None:
        """Parse an enterprise system with nested sub-systems."""
        source = """\
system Enterprise {
    title = "Enterprise Landscape"

    system ECommerce {}
    system Warehouse {}

    connect ECommerce -> Warehouse by InventorySync
}
"""
        result = _parse(source)
        enterprise = result.systems[0]
        assert enterprise.title == "Enterprise Landscape"
        assert len(enterprise.systems) == 2
        assert len(enterprise.connections) == 1
        assert enterprise.connections[0].interface.name == "InventorySync"

    def test_bidirectional_connections(self) -> None:
        """Two connections simulate bidirectional communication."""
        source = """\
system S {
    connect ServiceA -> ServiceB by RequestToB
    connect ServiceB -> ServiceA by ResponseToA
}
"""
        result = _parse(source)
        conns = result.systems[0].connections
        assert len(conns) == 2
        assert conns[0].source.entity == "ServiceA"
        assert conns[1].source.entity == "ServiceB"


# ###############
# Error Handling
# ###############


class TestParseErrors:
    def test_unexpected_token_at_top_level(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            _parse("requires X")
        assert "Unexpected token" in str(exc_info.value)

    def test_missing_identifier_after_component(self) -> None:
        with pytest.raises(ParseError):
            _parse("component { }")

    def test_missing_lbrace_after_component_name(self) -> None:
        with pytest.raises(ParseError):
            _parse("component X requires Y")

    def test_missing_rbrace_closes_component(self) -> None:
        with pytest.raises(ParseError):
            _parse("component X {")

    def test_missing_identifier_after_system(self) -> None:
        with pytest.raises(ParseError):
            _parse("system { }")

    def test_missing_lbrace_after_system_name(self) -> None:
        with pytest.raises(ParseError):
            _parse("system X component Y {}")

    def test_missing_identifier_after_enum(self) -> None:
        with pytest.raises(ParseError):
            _parse("enum { Active }")

    def test_missing_rbrace_closes_enum(self) -> None:
        with pytest.raises(ParseError):
            _parse("enum Status { Pending")

    def test_missing_identifier_after_type(self) -> None:
        with pytest.raises(ParseError):
            _parse("type { field x: String }")

    def test_missing_identifier_after_interface(self) -> None:
        with pytest.raises(ParseError):
            _parse("interface { field x: String }")

    def test_unexpected_token_in_component_body(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            _parse("component X { import foo }")
        assert "Unexpected token" in str(exc_info.value)

    def test_unexpected_token_in_system_body(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            _parse("system S { import foo }")
        assert "Unexpected token" in str(exc_info.value)

    def test_unexpected_token_in_enum_body(self) -> None:
        with pytest.raises(ParseError):
            _parse("enum Status { Pending = 1 }")

    def test_unexpected_token_in_type_body(self) -> None:
        with pytest.raises(ParseError):
            _parse("type T { requires X }")

    def test_unexpected_token_in_interface_body(self) -> None:
        with pytest.raises(ParseError):
            _parse("interface I { requires X }")

    def test_external_followed_by_invalid_keyword(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            _parse("external interface I {}")
        assert "Expected" in str(exc_info.value)

    def test_use_followed_by_invalid_keyword(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            _parse("system S { use interface I }")
        assert "Expected" in str(exc_info.value)

    def test_connect_missing_arrow(self) -> None:
        with pytest.raises(ParseError):
            _parse("system S { connect A B by Interface }")

    def test_connect_missing_by(self) -> None:
        with pytest.raises(ParseError):
            _parse("system S { connect A -> B Interface }")

    def test_connect_missing_target(self) -> None:
        with pytest.raises(ParseError):
            _parse("system S { connect A -> by Interface }")

    def test_connect_missing_interface(self) -> None:
        with pytest.raises(ParseError):
            _parse("system S { connect A -> B by }")

    def test_field_missing_colon(self) -> None:
        with pytest.raises(ParseError):
            _parse("type T { field x String }")

    def test_field_missing_type(self) -> None:
        with pytest.raises(ParseError):
            _parse("type T { field x: }")

    def test_list_type_missing_rangle(self) -> None:
        with pytest.raises(ParseError):
            _parse("type T { field x: List<String }")

    def test_map_type_missing_comma(self) -> None:
        with pytest.raises(ParseError):
            _parse("type T { field x: Map<String String> }")

    def test_map_type_missing_rangle(self) -> None:
        with pytest.raises(ParseError):
            _parse("type T { field x: Map<String, Int }")

    def test_optional_type_missing_rangle(self) -> None:
        with pytest.raises(ParseError):
            _parse("type T { field x: Optional<String }")

    def test_tags_missing_equals(self) -> None:
        with pytest.raises(ParseError):
            _parse('component X { tags ["tag"] }')

    def test_tags_missing_lbracket(self) -> None:
        with pytest.raises(ParseError):
            _parse('component X { tags = "tag" }')

    def test_tags_missing_rbracket(self) -> None:
        with pytest.raises(ParseError):
            _parse('component X { tags = ["tag" }')

    def test_title_missing_equals(self) -> None:
        with pytest.raises(ParseError):
            _parse('component X { title "My Title" }')

    def test_title_missing_string(self) -> None:
        with pytest.raises(ParseError):
            _parse("component X { title = SomeIdentifier }")

    def test_import_missing_from_path(self) -> None:
        with pytest.raises(ParseError):
            _parse("from import X")

    def test_import_missing_import_keyword(self) -> None:
        with pytest.raises(ParseError):
            _parse("from interfaces/order X")

    def test_unknown_connection_attribute(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            _parse("system S { connect A -> B by I { timeout = 30 } }")
        assert "Unknown connection attribute" in str(exc_info.value)

    def test_unknown_field_annotation(self) -> None:
        with pytest.raises(ParseError):
            _parse("type T { field x: String { required = true } }")

    def test_error_has_line_number(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            _parse("\n\nrequires X")
        error = exc_info.value
        assert error.line == 3

    def test_error_has_column_number(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            _parse("   requires X")
        error = exc_info.value
        assert error.column == 4

    def test_error_message_includes_line_column(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            _parse("requires X")
        assert "Line" in str(exc_info.value)
        assert "column" in str(exc_info.value)

    def test_external_inside_component_body_non_component_raises(self) -> None:
        with pytest.raises(ParseError) as exc_info:
            _parse("component X { external system S {} }")
        assert "Expected" in str(exc_info.value)


# ###############
# Edge Cases
# ###############


class TestEdgeCases:
    def test_component_with_empty_tags(self) -> None:
        result = _parse("component X { tags = [] }")
        assert result.components[0].tags == []

    def test_interface_version_with_alphanumeric(self) -> None:
        result = _parse("interface X @v10 {}")
        assert result.interfaces[0].version == "v10"

    def test_connection_interface_version(self) -> None:
        result = _parse("system S { connect A -> B by Interface @v2 }")
        conn = result.systems[0].connections[0]
        assert conn.interface.version == "v2"

    def test_requires_with_version(self) -> None:
        result = _parse("component X { requires Interface @v2 }")
        assert result.components[0].requires[0].version == "v2"

    def test_provides_with_version(self) -> None:
        result = _parse("component X { provides Interface @v1 }")
        assert result.components[0].provides[0].version == "v1"

    def test_comments_in_source(self) -> None:
        source = """\
// Top-level comment
component X {
    // Inner comment
    /* Block comment */
    requires Y
}
"""
        result = _parse(source)
        assert result.components[0].requires[0].name == "Y"

    def test_type_with_file_field(self) -> None:
        source = """\
type Config {
    field app_config: File {
        filetype = "YAML"
        schema = "Top-level keys: server, database, logging."
    }
}
"""
        result = _parse(source)
        t = result.types[0]
        field = t.fields[0]
        assert isinstance(field.type, FileTypeRef)
        assert field.filetype == "YAML"
        assert "server" in field.schema  # type: ignore[operator]

    def test_type_with_directory_field(self) -> None:
        source = """\
type Artifact {
    field output: Directory {
        schema = "Contains manifests/*.yaml, config/app.yaml"
    }
}
"""
        result = _parse(source)
        field = result.types[0].fields[0]
        assert isinstance(field.type, DirectoryTypeRef)
        assert "manifests" in field.schema  # type: ignore[operator]

    def test_enum_values_preserve_order(self) -> None:
        source = "enum Color { Red Green Blue }"
        result = _parse(source)
        assert result.enums[0].values == ["Red", "Green", "Blue"]

    def test_interface_fields_preserve_order(self) -> None:
        source = """\
interface I {
    field a: String
    field b: Int
    field c: Bool
}
"""
        result = _parse(source)
        fields = result.interfaces[0].fields
        assert [f.name for f in fields] == ["a", "b", "c"]

    def test_deeply_nested_system(self) -> None:
        source = """\
system L1 {
    system L2 {
        system L3 {
            component X {}
        }
    }
}
"""
        result = _parse(source)
        l1 = result.systems[0]
        l2 = l1.systems[0]
        l3 = l2.systems[0]
        assert l3.components[0].name == "X"

    def test_external_component_inside_system(self) -> None:
        source = """\
system S {
    external component ThirdPartySDK {
        requires Config
        provides Data
    }
}
"""
        result = _parse(source)
        comp = result.systems[0].components[0]
        assert comp.is_external is True
        assert comp.name == "ThirdPartySDK"

    def test_external_system_inside_system(self) -> None:
        source = """\
system S {
    external system LegacyPlatform {
        provides LegacyData
    }
}
"""
        result = _parse(source)
        sub = result.systems[0].systems[0]
        assert sub.is_external is True
        assert sub.name == "LegacyPlatform"

    def test_string_with_special_characters(self) -> None:
        source = 'component X { title = "gRPC/HTTP2 Service (v2.0)" }'
        result = _parse(source)
        assert result.components[0].title == "gRPC/HTTP2 Service (v2.0)"

    def test_all_primitive_types_in_interface(self) -> None:
        source = """\
interface AllPrimitives {
    field s: String
    field i: Int
    field f: Float
    field d: Decimal
    field b: Bool
    field by: Bytes
    field ts: Timestamp
    field dt: Datetime
}
"""
        result = _parse(source)
        iface = result.interfaces[0]
        assert len(iface.fields) == 8
        expected = [
            PrimitiveType.STRING,
            PrimitiveType.INT,
            PrimitiveType.FLOAT,
            PrimitiveType.DECIMAL,
            PrimitiveType.BOOL,
            PrimitiveType.BYTES,
            PrimitiveType.TIMESTAMP,
            PrimitiveType.DATETIME,
        ]
        for field, ptype in zip(iface.fields, expected, strict=True):
            assert isinstance(field.type, PrimitiveTypeRef)
            assert field.type.primitive == ptype

    def test_use_component_creates_stub_with_correct_name(self) -> None:
        result = _parse("system S { use component MyComponent }")
        stub = result.systems[0].components[0]
        assert stub.name == "MyComponent"
        assert stub.requires == []
        assert stub.provides == []

    def test_use_system_creates_stub_with_correct_name(self) -> None:
        result = _parse("system S { use system SubSystem }")
        stub = result.systems[0].systems[0]
        assert stub.name == "SubSystem"

    def test_map_with_named_key_and_value(self) -> None:
        source = "type T { field m: Map<OrderId, OrderItem> }"
        result = _parse(source)
        map_type = result.types[0].fields[0].type
        assert isinstance(map_type, MapTypeRef)
        assert isinstance(map_type.key_type, NamedTypeRef)
        assert map_type.key_type.name == "OrderId"
        assert isinstance(map_type.value_type, NamedTypeRef)
        assert map_type.value_type.name == "OrderItem"

    def test_connection_without_annotation_block(self) -> None:
        result = _parse("system S { connect A -> B by X }")
        conn = result.systems[0].connections[0]
        assert conn.protocol is None
        assert conn.is_async is False
        assert conn.description is None

    def test_interface_field_empty_annotation_block(self) -> None:
        source = "interface I { field x: String {} }"
        result = _parse(source)
        field = result.interfaces[0].fields[0]
        assert field.description is None
        assert field.schema is None
