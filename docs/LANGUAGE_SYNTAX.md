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
# Line comments start with a hash sign.
```

Strings use double quotes. Identifiers are unquoted alphanumeric names with underscores (e.g., `order_service`). Every named entity has an optional human-readable `title` and `description`.

Multi-line text is written with triple-quoted strings (`"""`):

```
description = """
Accepts and validates customer orders.
Delegates payment processing to the PaymentGateway
and inventory checks to the InventoryManager.
"""
```

Single-quoted strings may not contain a literal newline character but support the same `\n`, `\t`, `\\`, `\"` escape sequences as triple-quoted strings.

## Type System

### Primitive Types

`String`, `Int`, `Float`, `Decimal`, `Bool`, `Bytes`, `Timestamp`, `Datetime`

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

The `enum` keyword defines a constrained set of named values. Each value must appear on its own line:

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
    field total_amount: Decimal {
        description = "Grand total including tax and shipping."
    }
    field currency: String {
        description = "ISO 4217 currency code."
        schema = "Three-letter uppercase code, e.g. USD, EUR."
    }
}
```

Fields support optional `description` and `schema` annotations in a block. `description` explains the purpose of the field; `schema` provides format or validation expectations as free text.

Interfaces support versioning with the `@` suffix:

```
interface OrderRequest @v2 {
    field order_id: String
    field customer_id: String
    field items: List<OrderItem>
    field total_amount: Decimal
    field currency: String
    field shipping_method: String
}
```

When a component requires or provides a versioned interface, it references the version explicitly (e.g., `requires OrderRequest @v2`). Unversioned references default to the latest version.

`interface` defines a contract used on ports. `type` defines a building block used within interfaces. Both share the same field syntax — the distinction is semantic: interfaces appear on ports; types compose into fields.

### Component

A component is a module with a clear responsibility. Components declare the interfaces they **require** (consume) and **provide** (expose) as **ports**. `requires` declarations always come before `provides`.

```
component OrderService {
    title = "Order Service"
    description = "Accepts and validates customer orders."

    requires PaymentRequest
    requires InventoryCheck
    provides OrderConfirmation
}
```

Each `requires` or `provides` declaration directly on an entity defines one of its **own ports** — a named connection point at its boundary. Own ports do not need `expose`; they are the entity's interface. By default, the port name equals the interface name. Use `as` to assign an explicit name when needed:

```
component OrderService {
    requires PaymentRequest as pay_in
    requires InventoryCheck as inv_in
    provides OrderConfirmation as confirmed
}
```

Components can nest sub-components to express internal structure. `connect` statements wire sub-components together without coupling them directly. Every port of every sub-component must either be wired by a `connect` or explicitly promoted to the enclosing boundary with `expose`:

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

    // Wire Validator output to Processor input via an implicit channel
    connect Validator.ValidationResult -> $validation -> Processor.ValidationResult

    // All remaining ports must be explicitly promoted to the OrderService boundary
    expose Validator.OrderRequest
    expose Processor.PaymentRequest
    expose Processor.InventoryCheck
    expose Processor.OrderConfirmation
}
```

A port that is neither wired by `connect` nor promoted by `expose` is a validation error.

### System

A system groups components (or sub-systems) that work toward a shared goal. Systems wire their members using `connect` statements. Systems may contain components and other systems, but components may not contain systems.

```
system ECommerce {
    title = "E-Commerce Platform"
    description = "Customer-facing online store."

    component OrderService {
        requires PaymentRequest
        requires InventoryCheck
        provides OrderConfirmation
    }

    component PaymentGateway {
        provides PaymentRequest
    }

    component InventoryManager {
        provides InventoryCheck
    }

    connect PaymentGateway.PaymentRequest -> $payment -> OrderService.PaymentRequest {
        protocol = "gRPC"
        async = true
    }
    connect InventoryManager.InventoryCheck -> $inventory -> OrderService.InventoryCheck {
        protocol = "HTTP"
    }

    // OrderService.OrderConfirmation has no internal consumer — expose it as the
    // system's own boundary port
    expose OrderService.OrderConfirmation
}
```

Systems can nest other systems for large-scale decomposition:

```
system Enterprise {
    title = "Enterprise Landscape"

    system ECommerce {
        provides InventorySync   // declared directly — ECommerce's own boundary port
    }

    system Warehouse {
        requires InventorySync   // declared directly — Warehouse's own boundary port
    }

    connect ECommerce.InventorySync -> $inventory_sync -> Warehouse.InventorySync
}
```

### User

A user represents a human actor — a role or persona that interacts with the system. Users declare the interfaces they **require** (consume from components, such as data they receive) and **provide** (expose to components, such as form inputs or commands).

```
user Customer {
    title = "Customer"
    description = "An end user who places orders through the e-commerce platform."

    provides OrderRequest
    requires OrderConfirmation
}
```

Users are leaf nodes — they cannot contain components or sub-users. A user participates in `connect` statements like any other entity:

```
system ECommerce {
    user Customer {
        provides OrderRequest
        requires OrderConfirmation
    }

    component OrderService {
        requires OrderRequest
        provides OrderConfirmation
    }

    connect Customer.OrderRequest -> $order_in -> OrderService.OrderRequest
    connect OrderService.OrderConfirmation -> $order_out -> Customer.OrderConfirmation
}
```

### External Actors

The `external` keyword marks systems, components, or users that are outside the development boundary:

```
external system StripeAPI {
    title = "Stripe Payment API"
    requires PaymentRequest
    provides PaymentResult
}

external user Admin {
    title = "System Administrator"
    provides AdminCommand
}
```

External entities appear in diagrams with distinct styling. They cannot be further decomposed (they are opaque).

## Ports and Channels

### Ports

Every `requires` and `provides` declaration defines a **port** — a named connection point on the entity. The port name defaults to the interface name; use `as` to assign an explicit name:

```
requires <Interface> [@version] [as <port_name>]
provides <Interface> [@version] [as <port_name>]
```

```
requires PaymentRequest                   // port named "PaymentRequest"
requires PaymentRequest as pay_in         // port named "pay_in"
provides OrderConfirmation as confirmed   // port named "confirmed"
```

Port names must be unique within their entity. When two sub-entities have ports with the same name and both are promoted via `expose`, use `as` to disambiguate.

### Channels and the `connect` Statement

A **channel** is a named conduit between ports. Channels are introduced implicitly by `connect` statements — there is no separate channel declaration. Channel names use the `$` prefix to distinguish them from port names.

The `connect` statement has three forms:

```
// Full chain: introduces $channel and wires both ports in one statement
connect <src_port> -> $<channel> -> <dst_port>

// One-sided: introduces or references $channel, wires one port
connect <src_port> -> $<channel>
connect $<channel> -> <dst_port>

// Direct: wires two ports without a named channel
connect <src_port> -> <dst_port>
```

`<src_port>` and `<dst_port>` are either:

- `Entity.port_name` — a port on a named child entity
- `port_name` — a port on the current scope's own boundary

The arrow direction follows data flow: a `provides` port (producer) is always on the left; a `requires` port (consumer) is always on the right. The tooling validates that the interface types on both sides of a channel are compatible.

```
// Full chain — introduces $payment and wires both sides at once
connect PaymentGateway.PaymentRequest -> $payment -> OrderService.PaymentRequest

// Multi-step — build up a channel across two statements (same result)
connect PaymentGateway.PaymentRequest -> $payment
connect $payment -> OrderService.PaymentRequest

// Direct connection without a named channel
connect Validator.ValidationResult -> Processor.ValidationResult
```

Channel attributes (`protocol`, `async`, `description`) can be set in an optional block on the `connect` statement that introduces the channel:

```
connect PaymentGateway.PaymentRequest -> $payment -> OrderService.PaymentRequest {
    protocol = "gRPC"
    async = true
    description = "Delegate payment processing to Stripe."
}
```

| Attribute     | Type    | Purpose                                      |
| ------------- | ------- | -------------------------------------------- |
| `protocol`    | string  | Transport protocol (e.g. `"gRPC"`, `"HTTP"`) |
| `async`       | boolean | Whether the channel is asynchronous          |
| `description` | string  | Human-readable explanation of the channel    |

### Port Exposure

Every port of every sub-entity must be accounted for within its enclosing scope: either wired by a `connect` statement or explicitly promoted to the enclosing boundary with `expose`. A port that is neither wired nor exposed is a **validation error**.

```
expose Entity.port_name [as new_name]
```

`expose` promotes a sub-entity's port to the enclosing boundary, making it part of that scope's own interface. The optional `as` renames the port at the boundary:

```
component OrderService {
    component Processor {
        requires PaymentRequest
        provides OrderConfirmation
    }

    expose Processor.PaymentRequest as pay_in     // promoted and renamed
    expose Processor.OrderConfirmation            // promoted under the same name
}
```

`expose` composes across levels: a system can wire a component's exposed port directly, or expose it further up to the system's own boundary:

```
system ECommerce {
    use component OrderService   // OrderService exposes PaymentRequest

    component PaymentGateway {
        provides PaymentRequest
    }

    // Wire the exposed port — this also satisfies it (no separate expose needed)
    connect PaymentGateway.PaymentRequest -> $payment -> OrderService.PaymentRequest
}
```

At the top level of a system, ports that are not wired to any sibling must be exposed to declare that the system itself requires or provides that interface from/to the outside world:

```
system ECommerce {
    component OrderService {
        requires OrderRequest
        provides OrderConfirmation
    }

    // No internal component provides OrderRequest or consumes OrderConfirmation —
    // expose them as the system's own boundary:
    expose OrderService.OrderRequest
    expose OrderService.OrderConfirmation
}
```

### Encapsulation

A channel introduced by a `connect` statement is local to the scope where it appears — it is not visible from outside. The `$` prefix makes channels syntactically distinct from ports, preventing accidental name collisions.

## Tags

Any named entity can carry **tags** for filtering and view generation:

```
component PaymentGateway {
    tags = ["critical", "pci-scope"]
    ...
}
```

## Multi-File Composition

Large architectures are split across files. The `from ... import` statement brings specific named definitions from other files into scope. The `use` keyword places an imported entity into a system or parent component without redefining it. `use` always includes the entity type for clarity.

Components, interfaces, types, and enums can all be defined at the top level of any `.archml` file — they do not need to be nested inside a system. This enables a one-file-per-component workflow where each component is self-contained and systems compose them by reference.

### Explicit Imports

Imports name the exact entities to bring into scope. The path omits the `.archml` extension and is resolved using the repository's virtual filesystem mapping (see [Repository Configuration](#repository-configuration)):

```
from dir/subdir/file import Entity
from dir/subdir/file import Entity1, Entity2
```

```
// file: interfaces/order.archml
interface OrderRequest { ... }
interface OrderConfirmation { ... }

// file: components/order_service.archml
from interfaces/order import OrderRequest, OrderConfirmation

component OrderService {
    title = "Order Service"

    requires OrderRequest
    provides OrderConfirmation
}

// file: systems/ecommerce.archml
from interfaces/order import OrderRequest, OrderConfirmation, PaymentRequest, InventoryCheck
from components/order_service import OrderService

system ECommerce {
    title = "E-Commerce Platform"

    use component OrderService

    component PaymentGateway {
        provides PaymentRequest
    }

    // Wire the imported component's surfaced port to the inline component's port
    connect PaymentGateway.PaymentRequest -> $payment -> OrderService.PaymentRequest
}
```

The `use` keyword places an already-imported entity in scope. Its exposed ports become available as `Entity.port_name` targets in `connect` and `expose` statements within the enclosing scope.

### Cross-Repository Imports

Architecture from multiple repositories can be combined into a unified architecture picture. To import from another repository, prefix the path with `@repo-name`:

```
from @repo/top-level-name/dir/subdir/file import Entity
```

When `@repo` is omitted, the current repository is used. The `repo-name` refers to a named repository declared in the workspace configuration (see [Workspace Configuration](#workspace-configuration)).

```
// Importing from the current repository (@ prefix omitted)
from interfaces/order import OrderRequest

// Importing from named repositories
from @payments/services/payment import PaymentService
from @inventory/services/stock import StockManager

system Enterprise {
    title = "Enterprise Landscape"

    use component OrderService
    use component PaymentService
    use component StockManager
}
```

## Repository Configuration

Each repository defines a virtual filesystem mapping in an `archml.yaml` file at the repository root. The mapping assigns short top-level names to paths relative to the repository root, creating stable import roots that are decoupled from the physical directory layout:

```yaml
# archml.yaml
roots:
  interfaces: src/architecture/interfaces
  components: src/architecture/components
  systems: src/architecture/systems
  types: src/architecture/types
```

An import path is resolved by matching its first segment against the declared top-level names. For example, the path `interfaces/order` resolves to `src/architecture/interfaces/order.archml`. A path whose first segment does not match any declared name is a resolution error.

Top-level names can map to individual files as well as directories. Both same-repository and cross-repository imports use the virtual filesystem mapping of the repository being imported from.

## Workspace Configuration

Cross-repository imports require a workspace configuration (`archml-workspace.yaml`) at the workspace root that lists the repositories available for import:

```yaml
# archml-workspace.yaml
repositories:
  payments:
    url: https://github.com/example/payments-service
    ref: main
  inventory:
    url: https://github.com/example/inventory-service
    ref: v2.3.0
```

The key (e.g., `payments`) matches the `@repo-name` prefix in import paths. The `ref` field pins the import to a specific branch, tag, or commit.

## Complete Example

```
// archml.yaml (project configuration)
// roots:
//   types: types.archml
//   components: components
//   systems: systems

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

interface ValidationResult {
    field order_id: String
    field valid: Bool
}

interface ReportOutput {
    field report: File {
        filetype = "PDF"
        schema = "Monthly sales summary report."
    }
}

// file: components/order_service.archml
from types import OrderRequest, ValidationResult, PaymentRequest, InventoryCheck, OrderConfirmation

component OrderService {
    title = "Order Service"
    description = "Accepts, validates, and processes customer orders."

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

    // Wire Validator to Processor internally
    connect Validator.ValidationResult -> $validation -> Processor.ValidationResult

    // Expose the remaining ports at the OrderService boundary
    expose Validator.OrderRequest
    expose Processor.PaymentRequest
    expose Processor.InventoryCheck
    expose Processor.OrderConfirmation
}

// file: systems/ecommerce.archml
from types import OrderRequest, OrderConfirmation, PaymentRequest, PaymentResult, InventoryCheck, InventoryStatus
from components/order_service import OrderService

system ECommerce {
    title = "E-Commerce Platform"

    user Customer {
        title = "Customer"
        description = "An end user who places orders through the e-commerce platform."

        provides OrderRequest
        requires OrderConfirmation
    }

    use component OrderService

    component PaymentGateway {
        title = "Payment Gateway"
        tags = ["critical", "pci-scope"]

        provides PaymentRequest
        requires PaymentResult
    }

    component InventoryManager {
        title = "Inventory Manager"

        provides InventoryCheck
    }

    external system StripeAPI {
        title = "Stripe Payment API"
        requires PaymentRequest
        provides PaymentResult
    }

    // Wire Customer to OrderService
    connect Customer.OrderRequest -> $order_in -> OrderService.OrderRequest
    connect OrderService.OrderConfirmation -> $order_out -> Customer.OrderConfirmation

    // Wire OrderService to backing services
    connect PaymentGateway.PaymentRequest -> $payment -> OrderService.PaymentRequest {
        protocol = "gRPC"
        async = true
        description = "Delegate payment processing."
    }
    connect InventoryManager.InventoryCheck -> $inventory -> OrderService.InventoryCheck {
        protocol = "HTTP"
    }

    // Wire PaymentGateway to external Stripe
    connect PaymentGateway.PaymentRequest -> $stripe -> StripeAPI.PaymentRequest
    connect StripeAPI.PaymentResult -> $stripe_result -> PaymentGateway.PaymentResult
}
```

## Summary of Keywords

| Keyword         | Purpose                                                                                                            |
| --------------- | ------------------------------------------------------------------------------------------------------------------ |
| `system`        | Group of components or sub-systems with a shared goal.                                                             |
| `component`     | Module with a clear responsibility; may nest sub-components.                                                       |
| `user`          | Human actor (role or persona) that interacts with the system; a leaf node.                                         |
| `interface`     | Named contract of typed data fields. Supports versioning via `@v1`, `@v2`, etc.                                    |
| `type`          | Reusable data structure (used within interfaces).                                                                  |
| `enum`          | Constrained set of named values.                                                                                   |
| `field`         | Named, typed data element. Supports `description` and `schema` annotations.                                        |
| `filetype`      | Annotation on a `File` field specifying its format.                                                                |
| `schema`        | Free-text annotation describing expected content or format.                                                        |
| `requires`      | Declares a port that consumes an interface (listed before `provides`).                                             |
| `provides`      | Declares a port that exposes an interface.                                                                         |
| `as`            | Assigns an explicit name to a port (`requires PaymentRequest as pay_in`).                                          |
| `connect`       | Wires ports together, optionally via a named channel (`connect A.p -> $ch -> B.p`).                                |
| `expose`        | Explicitly surfaces a sub-entity's port at the enclosing boundary (`expose Entity.port [as name]`).               |
| `$channel`      | Channel name in a `connect` statement; `$` prefix distinguishes channels from ports.                               |
| `from`          | Introduces the source path in an import statement (`from path import Name`).                                       |
| `import`        | Names the specific entities to bring into scope; always paired with `from` (`from path import Name`).              |
| `use`           | Places an imported entity into a system or component (e.g., `use component X`).                                    |
| `external`      | Marks a system, component, or user as outside the development boundary.                                            |
| `tags`          | Arbitrary labels for filtering and view generation.                                                                |
| `title`         | Human-readable display name.                                                                                       |
| `description`   | Longer explanation of an entity's purpose.                                                                         |

## Scope Boundaries

- **Views** are not part of the architecture language syntax. They are defined in a separate view DSL that references entities from the architecture model.
