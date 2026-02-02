# ArchML — Language Syntax (Functional Architecture)

## Design Goals

1. **Readable without tooling** — An `.archml` file should read like structured prose, not code. Architects unfamiliar with the DSL should grasp the intent within minutes.
2. **Minimal ceremony** — Common patterns require few keywords. Boilerplate is the enemy of adoption.
3. **Composable** — Large architectures split across multiple files. Each file is self-contained but can reference definitions from others.
4. **Validatable** — The syntax carries enough semantic information for tooling to detect inconsistencies (dangling references, unused interfaces, disconnected components).
5. **Extensible** — The core syntax covers functional architecture; behavioral and deployment domains will extend it later without breaking existing files.

## File Structure

ArchML files use the `.archml` extension. A file contains one or more top-level declarations. Declarations can be nested to express containment.

```
// Line comments start with double slashes.

/* Block comments are also supported. */
```

Strings use double quotes. Identifiers are unquoted alphanumeric names with underscores (e.g., `order_service`). Every named entity has an optional human-readable `title` and `description`.

## Core Entities

### Interface

An interface defines a contract — a named set of typed data fields exchanged between architectural elements. Interfaces are declared at the top level or inside components and systems.

```
interface OrderRequest {
    title = "Order Creation Request"
    description = "Payload for submitting a new customer order."

    field order_id: String
    field customer_id: String
    field items: List<OrderItem>
    field total_amount: Decimal
    field currency: String
}
```

**Supported primitive types**: `String`, `Int`, `Float`, `Decimal`, `Bool`, `Bytes`, `Timestamp`.

**Generic container types**: `List<T>`, `Map<K, V>`, `Optional<T>`.

**Custom types** are referenced by name. The tooling resolves them to other interface or type definitions:

```
type OrderItem {
    field product_id: String
    field quantity: Int
    field unit_price: Decimal
}
```

`type` defines a reusable data structure. `interface` defines a contract used in connections. Both share the same field syntax — the distinction is semantic: interfaces appear on ports; types are building blocks.

### Component

A component is a module with a clear responsibility. Components declare the interfaces they **provide** (expose to others) and **require** (consume from others).

```
component OrderService {
    title = "Order Service"
    description = "Accepts and validates customer orders."

    provides OrderConfirmation
    requires PaymentRequest
    requires InventoryCheck
}
```

Components can be **composed** of sub-components to express internal structure:

```
component OrderService {
    title = "Order Service"

    component Validator {
        title = "Order Validator"
        description = "Validates order contents and business rules."

        provides ValidationResult
        requires OrderRequest
    }

    component Processor {
        title = "Order Processor"
        description = "Orchestrates payment and inventory checks."

        provides OrderConfirmation
        requires ValidationResult
        requires PaymentRequest
        requires InventoryCheck
    }

    // Internal wiring: Processor consumes what Validator produces.
    connect Validator.ValidationResult -> Processor.ValidationResult

    // Surface-level ports: what the parent component exposes.
    provides OrderConfirmation from Processor
    requires OrderRequest to Validator
    requires PaymentRequest from Processor
    requires InventoryCheck from Processor
}
```

### System

A system groups components (or sub-systems) that work toward a shared goal. Systems may contain components and other systems, but components may not contain systems.

```
system ECommerce {
    title = "E-Commerce Platform"
    description = "Customer-facing online store."

    component OrderService { ... }
    component PaymentGateway { ... }
    component InventoryManager { ... }

    // Connections between components within this system.
    connect OrderService.PaymentRequest -> PaymentGateway.PaymentRequest
    connect OrderService.InventoryCheck -> InventoryManager.InventoryCheck
}
```

Systems can nest other systems for large-scale decomposition:

```
system Enterprise {
    title = "Enterprise Landscape"

    system ECommerce { ... }
    system Warehouse { ... }

    // Cross-system connections.
    connect ECommerce.InventorySync -> Warehouse.InventorySync
}
```

## Connections

Connections are the data-flow edges of the architecture graph. A connection always links a **required** interface on one side to a **provided** interface on the other. The arrow `->` indicates the direction of the request (who initiates); data may flow in both directions as part of request/response.

```
connect <source>.<interface> -> <target>.<interface>
```

Connections may carry annotations:

```
connect OrderService.PaymentRequest -> PaymentGateway.PaymentRequest {
    protocol = "gRPC"
    async = true
    description = "Initiates payment processing for confirmed orders."
}
```

### Connection Semantics

| Annotation   | Type    | Description                                        |
|--------------|---------|----------------------------------------------------|
| `protocol`   | String  | Communication protocol (e.g., `"HTTP"`, `"gRPC"`, `"AMQP"`). |
| `async`      | Bool    | Whether the interaction is asynchronous.            |
| `description`| String  | Human-readable explanation of the interaction.      |

## Tags and Metadata

Any named entity can carry **tags** for filtering and view generation:

```
component PaymentGateway {
    tags = ["critical", "pci-scope", "external-dependency"]
    ...
}
```

Tags are arbitrary strings. Tooling can use them to generate filtered views (e.g., "show only PCI-scoped components").

## Multi-File Composition

Large architectures are split across files. The `import` statement brings definitions from other files into scope:

```
// file: interfaces/order.archml
interface OrderRequest { ... }
interface OrderConfirmation { ... }

// file: systems/ecommerce.archml
import "interfaces/order.archml"

system ECommerce {
    component OrderService {
        requires OrderRequest
        provides OrderConfirmation
    }
}
```

Import paths are relative to the project root (the directory containing the `.archml` files or a future configuration file).

## External Actors

Not every participant in the architecture is under the team's control. The `external` keyword marks systems or components that are outside the development boundary:

```
external system StripeAPI {
    title = "Stripe Payment API"
    provides PaymentResult
    requires PaymentRequest
}
```

External entities appear in diagrams with distinct styling. The tooling can enforce that external entities are not further decomposed (they are opaque).

## Constraints

Constraints express architectural rules that the tooling validates:

```
constraint "Every component must expose at least one interface" {
    forall component c: c.provides is not empty
}

constraint "External systems must not contain sub-components" {
    forall external system s: s.components is empty
}
```

Constraint syntax is deliberately kept close to natural language with a small formal core (`forall`, `exists`, `is`, `not`, `empty`, `and`, `or`). The exact constraint language will be refined as the tooling matures — the examples above illustrate the intent rather than a final grammar.

## Complete Example

```
// types.archml
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

interface OrderConfirmation {
    field order_id: String
    field status: String
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

// ecommerce.archml
import "types.archml"

external system StripeAPI {
    title = "Stripe Payment API"
    provides PaymentResult
    requires PaymentRequest
}

system ECommerce {
    title = "E-Commerce Platform"

    component OrderService {
        title = "Order Service"
        description = "Accepts, validates, and processes customer orders."

        provides OrderConfirmation
        requires OrderRequest
        requires PaymentRequest
        requires InventoryCheck
    }

    component PaymentGateway {
        title = "Payment Gateway"
        description = "Mediates between internal services and external payment providers."
        tags = ["critical", "pci-scope"]

        provides PaymentResult
        requires PaymentRequest
    }

    component InventoryManager {
        title = "Inventory Manager"
        description = "Tracks product stock levels."

        provides InventoryStatus
        requires InventoryCheck
    }

    connect OrderService.PaymentRequest -> PaymentGateway.PaymentRequest
    connect OrderService.InventoryCheck -> InventoryManager.InventoryCheck {
        protocol = "HTTP"
        async = false
    }
    connect PaymentGateway.PaymentRequest -> StripeAPI.PaymentRequest {
        protocol = "HTTP"
        async = true
    }
}
```

## Summary of Keywords

| Keyword     | Purpose                                                    |
|-------------|------------------------------------------------------------|
| `system`    | Group of components or sub-systems with a shared goal.     |
| `component` | Module with a clear responsibility; may nest sub-components. |
| `interface` | Named contract of typed data fields.                       |
| `type`      | Reusable data structure (used within interfaces).          |
| `field`     | Named, typed data element inside an interface or type.     |
| `provides`  | Declares an interface that an element exposes.             |
| `requires`  | Declares an interface that an element consumes.            |
| `connect`   | Links a required interface to a provided interface.        |
| `import`    | Brings definitions from another file into scope.           |
| `external`  | Marks a system or component as outside the development boundary. |
| `constraint`| Declares a validatable architectural rule.                 |
| `tags`      | Arbitrary labels for filtering and view generation.        |
| `title`     | Human-readable display name.                               |
| `description` | Longer explanation of an entity's purpose.              |

## Open Questions

- **Versioning**: Should interfaces support versioning (e.g., `interface OrderRequest @v2`)? This would enable backward-compatibility analysis.
- **Enumerations**: Should the type system include `enum` for constrained value sets (e.g., `enum OrderStatus { Pending, Confirmed, Shipped }`)?
- **Bidirectional connections**: The current `->` syntax models request direction. Should there be explicit `<->` for peer-to-peer or pub/sub patterns?
- **Views**: How should named views (filtered subsets of the model) be declared in the DSL vs. in a separate view configuration?
