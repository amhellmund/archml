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

## Type System

### Primitive Types

`String`, `Int`, `Float`, `Decimal`, `Bool`, `Bytes`, `Timestamp`

### File and Directory

`File` and `Directory` represent filesystem entities exchanged between components (configuration files, data exports, logs, etc.).

A `File` field specifies a `filetype` and an optional free-text `schema` describing the expected content:

```
field app_config: File {
    filetype = "YAML"
    schema = "Top-level keys: server, database, logging."
}
```

A `Directory` field specifies a `schema` describing the expected layout:

```
field artifact: Directory {
    schema = "Contains manifests/*.yaml, config/app.yaml, config/secrets.env, scripts/deploy.sh"
}
```

### Container Types

`List<T>`, `Map<K, V>`, `Optional<T>`

### Enumerations

The `enum` keyword defines a constrained set of named values:

```
enum OrderStatus {
    Pending
    Confirmed
    Shipped
    Delivered
    Cancelled
}
```

### Custom Types

The `type` keyword defines a reusable data structure:

```
type OrderItem {
    field product_id: String
    field quantity: Int
    field unit_price: Decimal
}
```

Custom types, enums, and interfaces can all be referenced by name as field types.

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

`interface` defines a contract used in connections. `type` defines a building block used within interfaces. Both share the same field syntax — the distinction is semantic: interfaces appear on ports; types compose into fields.

### Component

A component is a module with a clear responsibility. Components declare the interfaces they **require** (consume from others) and **provide** (expose to others). `requires` declarations always come before `provides`.

```
component OrderService {
    title = "Order Service"
    description = "Accepts and validates customer orders."

    requires PaymentRequest
    requires InventoryCheck
    provides OrderConfirmation
}
```

Components can nest sub-components to express internal structure:

```
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

    connect Validator.ValidationResult -> Processor.ValidationResult
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

    connect ECommerce.InventorySync -> Warehouse.InventorySync
}
```

### External Actors

The `external` keyword marks systems or components that are outside the development boundary:

```
external system StripeAPI {
    title = "Stripe Payment API"
    requires PaymentRequest
    provides PaymentResult
}
```

External entities appear in diagrams with distinct styling. They cannot be further decomposed (they are opaque).

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

## Tags

Any named entity can carry **tags** for filtering and view generation:

```
component PaymentGateway {
    tags = ["critical", "pci-scope"]
    ...
}
```

## Multi-File Composition

Large architectures are split across files. The `import` statement brings definitions from other files into scope. The `use` keyword places an imported entity into a system or parent component without redefining it. `use` always includes the entity type for clarity.

Components, interfaces, types, and enums can all be defined at the top level of any `.archml` file — they do not need to be nested inside a system. This enables a one-file-per-component workflow where each component is self-contained and systems compose them by reference.

```
// file: interfaces/order.archml
interface OrderRequest { ... }
interface OrderConfirmation { ... }

// file: components/order_service.archml
import "interfaces/order.archml"

component OrderService {
    title = "Order Service"

    requires OrderRequest
    provides OrderConfirmation
}

// file: systems/ecommerce.archml
import "interfaces/order.archml"
import "components/order_service.archml"

system ECommerce {
    title = "E-Commerce Platform"

    use component OrderService
}
```

Import paths are relative to the project root. The `use` keyword only places an already-defined entity; it does not allow overriding fields or interfaces.

## Complete Example

```
// file: types.archml

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

// file: components/order_service.archml
import "types.archml"

component OrderService {
    title = "Order Service"
    description = "Accepts, validates, and processes customer orders."

    requires OrderRequest
    requires PaymentRequest
    requires InventoryCheck
    provides OrderConfirmation
}

// file: systems/ecommerce.archml
import "types.archml"
import "components/order_service.archml"

external system StripeAPI {
    title = "Stripe Payment API"
    requires PaymentRequest
    provides PaymentResult
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

    connect OrderService.PaymentRequest -> PaymentGateway.PaymentRequest
    connect OrderService.InventoryCheck -> InventoryManager.InventoryCheck {
        protocol = "HTTP"
    }
    connect PaymentGateway.PaymentRequest -> StripeAPI.PaymentRequest {
        protocol = "HTTP"
        async = true
    }
}
```

## Summary of Keywords

| Keyword       | Purpose                                                    |
|---------------|------------------------------------------------------------|
| `system`      | Group of components or sub-systems with a shared goal.     |
| `component`   | Module with a clear responsibility; may nest sub-components. |
| `interface`   | Named contract of typed data fields.                       |
| `type`        | Reusable data structure (used within interfaces).          |
| `enum`        | Constrained set of named values.                           |
| `field`       | Named, typed data element inside an interface or type.     |
| `filetype`    | Annotation on a `File` field specifying its format.        |
| `schema`      | Free-text annotation describing expected file/directory content. |
| `requires`    | Declares an interface that an element consumes (listed before `provides`). |
| `provides`    | Declares an interface that an element exposes.             |
| `connect`     | Links a required interface to a provided interface.        |
| `import`      | Brings definitions from another file into scope.           |
| `use`         | Places an imported entity into a system or component (e.g., `use component X`). |
| `external`    | Marks a system or component as outside the development boundary. |
| `tags`        | Arbitrary labels for filtering and view generation.        |
| `title`       | Human-readable display name.                               |
| `description` | Longer explanation of an entity's purpose.                 |

## Open Questions

- **Versioning**: Should interfaces support versioning (e.g., `interface OrderRequest @v2`)? This would enable backward-compatibility analysis.
- **Bidirectional connections**: The current `->` syntax models request direction. Should there be explicit `<->` for peer-to-peer or pub/sub patterns?
- **Views**: How should named views (filtered subsets of the model) be declared in the DSL vs. in a separate view configuration?
