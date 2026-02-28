# Copyright 2026 ArchML Contributors
# SPDX-License-Identifier: Apache-2.0

"""High-level tests demonstrating how to construct the ArchML semantic model."""

from archml.model import (
    ArchFile,
    Component,
    Connection,
    ConnectionEndpoint,
    DirectoryTypeRef,
    EnumDef,
    FieldDef,
    FileTypeRef,
    ImportDeclaration,
    InterfaceDef,
    InterfaceRef,
    ListTypeRef,
    MapTypeRef,
    NamedTypeRef,
    OptionalTypeRef,
    PrimitiveType,
    PrimitiveTypeRef,
    System,
    TypeDef,
)


def test_primitive_field() -> None:
    """A field can reference a primitive type."""
    f = FieldDef(name="order_id", type=PrimitiveTypeRef(primitive=PrimitiveType.STRING))
    assert f.name == "order_id"
    assert isinstance(f.type, PrimitiveTypeRef)
    assert f.type.primitive == PrimitiveType.STRING


def test_container_type_refs() -> None:
    """List, Map, and Optional type refs wrap inner type refs."""
    list_ref = ListTypeRef(element_type=PrimitiveTypeRef(primitive=PrimitiveType.INT))
    map_ref = MapTypeRef(
        key_type=PrimitiveTypeRef(primitive=PrimitiveType.STRING),
        value_type=PrimitiveTypeRef(primitive=PrimitiveType.DECIMAL),
    )
    optional_ref = OptionalTypeRef(inner_type=PrimitiveTypeRef(primitive=PrimitiveType.STRING))

    assert list_ref.element_type == PrimitiveTypeRef(primitive=PrimitiveType.INT)
    assert map_ref.key_type == PrimitiveTypeRef(primitive=PrimitiveType.STRING)
    assert optional_ref.inner_type == PrimitiveTypeRef(primitive=PrimitiveType.STRING)


def test_named_type_ref() -> None:
    """A NamedTypeRef references a type, enum, or interface by name."""
    ref = NamedTypeRef(name="OrderItem")
    assert ref.name == "OrderItem"


def test_field_with_annotations() -> None:
    """A field can carry description and schema annotations."""
    f = FieldDef(
        name="currency",
        type=PrimitiveTypeRef(primitive=PrimitiveType.STRING),
        description="ISO 4217 currency code.",
        schema_ref="Three-letter uppercase code, e.g. USD, EUR.",
    )
    assert f.description == "ISO 4217 currency code."
    assert f.schema_ref == "Three-letter uppercase code, e.g. USD, EUR."
    assert f.filetype is None


def test_file_type_field() -> None:
    """A field can reference the File filesystem type with filetype and schema."""
    f = FieldDef(
        name="report",
        type=FileTypeRef(),
        filetype="PDF",
        schema_ref="Monthly sales summary report.",
    )
    assert isinstance(f.type, FileTypeRef)
    assert f.filetype == "PDF"
    assert f.schema_ref == "Monthly sales summary report."


def test_directory_type_field() -> None:
    """A field can reference the Directory filesystem type."""
    f = FieldDef(
        name="artifact",
        type=DirectoryTypeRef(),
        schema_ref="Contains manifests/*.yaml, config/app.yaml",
    )
    assert isinstance(f.type, DirectoryTypeRef)
    assert f.schema_ref == "Contains manifests/*.yaml, config/app.yaml"


def test_enum_definition() -> None:
    """An EnumDef holds a list of named values."""
    status = EnumDef(
        name="OrderStatus",
        values=["Pending", "Confirmed", "Shipped", "Delivered", "Cancelled"],
    )
    assert status.name == "OrderStatus"
    assert len(status.values) == 5
    assert "Shipped" in status.values


def test_type_definition() -> None:
    """A TypeDef holds named fields with typed references."""
    order_item = TypeDef(
        name="OrderItem",
        fields=[
            FieldDef(name="product_id", type=PrimitiveTypeRef(primitive=PrimitiveType.STRING)),
            FieldDef(name="quantity", type=PrimitiveTypeRef(primitive=PrimitiveType.INT)),
            FieldDef(name="unit_price", type=PrimitiveTypeRef(primitive=PrimitiveType.DECIMAL)),
        ],
    )
    assert order_item.name == "OrderItem"
    assert len(order_item.fields) == 3
    assert order_item.fields[0].name == "product_id"


def test_interface_definition() -> None:
    """An InterfaceDef describes a named contract with typed fields."""
    iface = InterfaceDef(
        name="OrderRequest",
        title="Order Creation Request",
        description="Payload for submitting a new customer order.",
        fields=[
            FieldDef(name="order_id", type=PrimitiveTypeRef(primitive=PrimitiveType.STRING)),
            FieldDef(name="customer_id", type=PrimitiveTypeRef(primitive=PrimitiveType.STRING)),
            FieldDef(
                name="items",
                type=ListTypeRef(element_type=NamedTypeRef(name="OrderItem")),
            ),
            FieldDef(name="total_amount", type=PrimitiveTypeRef(primitive=PrimitiveType.DECIMAL)),
        ],
    )
    assert iface.name == "OrderRequest"
    assert iface.version is None
    assert len(iface.fields) == 4
    items_field = iface.fields[2]
    assert isinstance(items_field.type, ListTypeRef)
    assert isinstance(items_field.type.element_type, NamedTypeRef)
    assert items_field.type.element_type.name == "OrderItem"


def test_versioned_interface() -> None:
    """An InterfaceDef can carry a version label."""
    iface = InterfaceDef(name="OrderRequest", version="v2")
    assert iface.version == "v2"


def test_component_with_requires_and_provides() -> None:
    """A Component declares its consumed and exposed interfaces."""
    svc = Component(
        name="OrderService",
        title="Order Service",
        description="Accepts and validates customer orders.",
        requires=[
            InterfaceRef(name="PaymentRequest"),
            InterfaceRef(name="InventoryCheck"),
        ],
        provides=[InterfaceRef(name="OrderConfirmation")],
    )
    assert svc.name == "OrderService"
    assert len(svc.requires) == 2
    assert len(svc.provides) == 1
    assert svc.requires[0].name == "PaymentRequest"
    assert not svc.is_external


def test_component_with_tags() -> None:
    """A Component can carry arbitrary tags."""
    gw = Component(
        name="PaymentGateway",
        tags=["critical", "pci-scope"],
        requires=[InterfaceRef(name="PaymentRequest")],
        provides=[InterfaceRef(name="PaymentResult")],
    )
    assert "critical" in gw.tags
    assert "pci-scope" in gw.tags


def test_external_component() -> None:
    """A Component can be marked as external."""
    ext = Component(name="StripeAPI", is_external=True)
    assert ext.is_external


def test_connection() -> None:
    """A Connection links a required interface to a provided interface."""
    conn = Connection(
        source=ConnectionEndpoint(entity="OrderService"),
        target=ConnectionEndpoint(entity="PaymentGateway"),
        interface=InterfaceRef(name="PaymentRequest"),
        protocol="gRPC",
        is_async=True,
        description="Initiates payment processing.",
    )
    assert conn.source.entity == "OrderService"
    assert conn.target.entity == "PaymentGateway"
    assert conn.interface.name == "PaymentRequest"
    assert conn.protocol == "gRPC"
    assert conn.is_async


def test_nested_component() -> None:
    """A Component can contain sub-components with internal connections."""
    validator = Component(
        name="Validator",
        requires=[InterfaceRef(name="OrderRequest")],
        provides=[InterfaceRef(name="ValidationResult")],
    )
    processor = Component(
        name="Processor",
        requires=[InterfaceRef(name="ValidationResult"), InterfaceRef(name="PaymentRequest")],
        provides=[InterfaceRef(name="OrderConfirmation")],
    )
    conn = Connection(
        source=ConnectionEndpoint(entity="Validator"),
        target=ConnectionEndpoint(entity="Processor"),
        interface=InterfaceRef(name="ValidationResult"),
    )
    order_svc = Component(
        name="OrderService",
        components=[validator, processor],
        connections=[conn],
    )
    assert len(order_svc.components) == 2
    assert len(order_svc.connections) == 1
    assert order_svc.components[0].name == "Validator"


def test_system_with_components_and_connections() -> None:
    """A System groups components and declares connections between them."""
    order_svc = Component(
        name="OrderService",
        requires=[InterfaceRef(name="PaymentRequest"), InterfaceRef(name="InventoryCheck")],
        provides=[InterfaceRef(name="OrderConfirmation")],
    )
    payment_gw = Component(
        name="PaymentGateway",
        tags=["critical", "pci-scope"],
        requires=[InterfaceRef(name="PaymentRequest")],
        provides=[InterfaceRef(name="PaymentResult")],
    )
    ecommerce = System(
        name="ECommerce",
        title="E-Commerce Platform",
        components=[order_svc, payment_gw],
        connections=[
            Connection(
                source=ConnectionEndpoint(entity="OrderService"),
                target=ConnectionEndpoint(entity="PaymentGateway"),
                interface=InterfaceRef(name="PaymentRequest"),
            )
        ],
    )
    assert ecommerce.name == "ECommerce"
    assert len(ecommerce.components) == 2
    assert len(ecommerce.connections) == 1
    assert not ecommerce.is_external


def test_nested_systems() -> None:
    """A System can contain sub-systems for large-scale decomposition."""
    ecommerce = System(name="ECommerce")
    warehouse = System(name="Warehouse")
    enterprise = System(
        name="Enterprise",
        systems=[ecommerce, warehouse],
        connections=[
            Connection(
                source=ConnectionEndpoint(entity="ECommerce"),
                target=ConnectionEndpoint(entity="Warehouse"),
                interface=InterfaceRef(name="InventorySync"),
            )
        ],
    )
    assert len(enterprise.systems) == 2
    assert enterprise.systems[0].name == "ECommerce"


def test_external_system() -> None:
    """A System can be marked as external."""
    stripe = System(name="StripeAPI", is_external=True)
    assert stripe.is_external


def test_import_declaration() -> None:
    """An ImportDeclaration captures a from/import statement."""
    imp = ImportDeclaration(
        source_path="interfaces/order",
        entities=["OrderRequest", "OrderConfirmation"],
    )
    assert imp.source_path == "interfaces/order"
    assert "OrderRequest" in imp.entities


def test_arch_file_composition() -> None:
    """An ArchFile holds all top-level declarations from a parsed .archml file."""
    arch = ArchFile(
        imports=[
            ImportDeclaration(
                source_path="interfaces/order",
                entities=["OrderRequest", "OrderConfirmation"],
            )
        ],
        enums=[
            EnumDef(
                name="OrderStatus",
                values=["Pending", "Confirmed", "Shipped"],
            )
        ],
        types=[
            TypeDef(
                name="OrderItem",
                fields=[
                    FieldDef(
                        name="product_id",
                        type=PrimitiveTypeRef(primitive=PrimitiveType.STRING),
                    ),
                    FieldDef(
                        name="quantity",
                        type=PrimitiveTypeRef(primitive=PrimitiveType.INT),
                    ),
                ],
            )
        ],
        interfaces=[
            InterfaceDef(
                name="OrderRequest",
                fields=[
                    FieldDef(
                        name="order_id",
                        type=PrimitiveTypeRef(primitive=PrimitiveType.STRING),
                    )
                ],
            )
        ],
        components=[
            Component(
                name="OrderService",
                requires=[InterfaceRef(name="OrderRequest")],
                provides=[InterfaceRef(name="OrderConfirmation")],
            )
        ],
        systems=[
            System(
                name="ECommerce",
                components=[Component(name="OrderService")],
            )
        ],
    )
    assert len(arch.imports) == 1
    assert len(arch.enums) == 1
    assert len(arch.types) == 1
    assert len(arch.interfaces) == 1
    assert len(arch.components) == 1
    assert len(arch.systems) == 1
    assert arch.enums[0].name == "OrderStatus"
    assert arch.types[0].name == "OrderItem"
