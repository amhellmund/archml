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

**Supported primitive types**: `String`, `Int`, `Float`, `Decimal`, `Bool`, `Bytes`, `Timestamp`, `File`, `Directory`.

**Generic container types**: `List<T>`, `Map<K, V>`, `Optional<T>`.

#### File and Directory Types

`File` and `Directory` are first-class primitives representing filesystem entities exchanged between components (configuration files, data exports, logs, etc.).

A **`File`** field specifies a `filetype` and an optional free-text `schema` describing the expected content:

```
interface ConfigInput {
    field app_config: File {
        filetype = "YAML"
        schema = "Top-level keys: server, database, logging. See docs/config-reference.md."
    }
    field tls_cert: File {
        filetype = "PEM"
    }
}
```

A **`Directory`** field describes a structured layout of nested files and subdirectories:

```
interface DeploymentBundle {
    field artifact: Directory {
        file manifests: File {
            filetype = "YAML"
            schema = "Kubernetes manifest files."
        }
        file readme: File {
            filetype = "Markdown"
        }
        directory config {
            file app: File {
                filetype = "YAML"
                schema = "Application configuration."
            }
            file secrets: File {
                filetype = "ENV"
                schema = "KEY=VALUE pairs for secret injection."
            }
        }
        directory scripts {
            file deploy: File {
                filetype = "Shell"
                schema = "Entry-point deployment script."
            }
        }
    }
}
```

Inside a `Directory` block, `file` declares a named file entry and `directory` declares a named subdirectory. Subdirectories nest recursively.

#### Enumerations

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

Enum values are plain identifiers. Enums can be used as field types just like primitives:

```
interface OrderUpdate {
    field order_id: String
    field status: OrderStatus
}
```

#### Custom Types

**Custom types** are referenced by name. The tooling resolves them to other interface, type, or enum definitions:

```
type OrderItem {
    field product_id: String
    field quantity: Int
    field unit_price: Decimal
}
```

`type` defines a reusable data structure. `interface` defines a contract used in connections. Both share the same field syntax — the distinction is semantic: interfaces appear on ports; types are building blocks.

### Component

A component is a module with a clear responsibility. Components declare the interfaces they **require** (consume from others) and **provide** (expose to others). By convention, `requires` declarations always come before `provides`.

```
component OrderService {
    title = "Order Service"
    description = "Accepts and validates customer orders."

    requires PaymentRequest
    requires InventoryCheck
    provides OrderConfirmation
}
```

Components can be **composed** of sub-components to express internal structure:

```
component OrderService {
    title = "Order Service"

    component Validator {
        title = "Order Validator"
        description = "Validates order contents and business rules."

        requires OrderRequest
        provides ValidationResult
    }

    component Processor {
        title = "Order Processor"
        description = "Orchestrates payment and inventory checks."

        requires ValidationResult
        requires PaymentRequest
        requires InventoryCheck
        provides OrderConfirmation
    }

    // Internal wiring: Processor consumes what Validator produces.
    connect Validator.ValidationResult -> Processor.ValidationResult

    // Surface-level ports: what the parent component exposes.
    requires OrderRequest to Validator
    requires PaymentRequest from Processor
    requires InventoryCheck from Processor
    provides OrderConfirmation from Processor
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

Large architectures are split across files. The `import` statement brings definitions from other files into scope. The `use` keyword places an imported entity (typically a component) into a system or parent component without redefining it.

Components, interfaces, types, and enums can all be defined at the top level of any `.archml` file — they do not need to be nested inside a system. This enables a one-file-per-component workflow where each component is self-contained and systems compose them by reference.

```
// file: interfaces/order.archml
interface OrderRequest { ... }
interface OrderConfirmation { ... }

// file: components/order_service.archml
import "interfaces/order.archml"

component OrderService {
    title = "Order Service"
    description = "Accepts, validates, and processes customer orders."

    requires OrderRequest
    provides OrderConfirmation
}

// file: systems/ecommerce.archml
import "interfaces/order.archml"
import "components/order_service.archml"

system ECommerce {
    title = "E-Commerce Platform"

    // Reference the imported component — no need to redefine it.
    use OrderService
}
```

Import paths are relative to the project root (the directory containing the `.archml` files or a future configuration file). The `use` keyword only places an already-defined entity; it does not allow overriding fields or interfaces.

## External Actors

Not every participant in the architecture is under the team's control. The `external` keyword marks systems or components that are outside the development boundary:

```
external system StripeAPI {
    title = "Stripe Payment API"
    requires PaymentRequest
    provides PaymentResult
}
```

External entities appear in diagrams with distinct styling. The tooling can enforce that external entities are not further decomposed (they are opaque).

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

    use OrderService

    component PaymentGateway {
        title = "Payment Gateway"
        description = "Mediates between internal services and external payment providers."
        tags = ["critical", "pci-scope"]

        requires PaymentRequest
        provides PaymentResult
    }

    component InventoryManager {
        title = "Inventory Manager"
        description = "Tracks product stock levels."

        requires InventoryCheck
        provides InventoryStatus
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

| Keyword       | Purpose                                                    |
|---------------|------------------------------------------------------------|
| `system`      | Group of components or sub-systems with a shared goal.     |
| `component`   | Module with a clear responsibility; may nest sub-components. |
| `interface`   | Named contract of typed data fields.                       |
| `type`        | Reusable data structure (used within interfaces).          |
| `enum`        | Constrained set of named values.                           |
| `field`       | Named, typed data element inside an interface or type.     |
| `file`        | Named file entry inside a `Directory` layout.              |
| `directory`   | Named subdirectory entry inside a `Directory` layout.      |
| `filetype`    | Annotation on a `File` specifying its format.              |
| `schema`      | Free-text annotation describing expected file content.     |
| `requires`    | Declares an interface that an element consumes (listed before `provides`). |
| `provides`    | Declares an interface that an element exposes.             |
| `connect`     | Links a required interface to a provided interface.        |
| `import`      | Brings definitions from another file into scope.           |
| `use`         | Places an imported entity into a system or component.      |
| `external`    | Marks a system or component as outside the development boundary. |
| `tags`        | Arbitrary labels for filtering and view generation.        |
| `title`       | Human-readable display name.                               |
| `description` | Longer explanation of an entity's purpose.                 |

## Open Questions

- **Versioning**: Should interfaces support versioning (e.g., `interface OrderRequest @v2`)? This would enable backward-compatibility analysis.
- **Bidirectional connections**: The current `->` syntax models request direction. Should there be explicit `<->` for peer-to-peer or pub/sub patterns?
- **Views**: How should named views (filtered subsets of the model) be declared in the DSL vs. in a separate view configuration?
