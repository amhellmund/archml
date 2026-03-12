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

`interface` defines a contract used in channels. `type` defines a building block used within interfaces. Both share the same field syntax — the distinction is semantic: interfaces appear on channels; types compose into fields.

### Component

A component is a module with a clear responsibility. Components declare the interfaces they **require** (consume) and **provide** (expose). `requires` declarations always come before `provides`.

```
component OrderService {
    title = "Order Service"
    description = "Accepts and validates customer orders."

    requires PaymentRequest
    requires InventoryCheck
    provides OrderConfirmation
}
```

Components can nest sub-components to express internal structure. Internal channels wire sub-components together without coupling them directly:

```
component OrderService {
    title = "Order Service"

    channel validation: ValidationResult

    component Validator {
        title = "Order Validator"

        requires OrderRequest
        provides ValidationResult via validation
    }

    component Processor {
        title = "Order Processor"

        requires ValidationResult via validation
        requires PaymentRequest
        requires InventoryCheck
        provides OrderConfirmation
    }
}
```

The `via` clause binds a `requires` or `provides` declaration to a named channel. Components that don't bind to a channel have unbound interface declarations, which are visible at the enclosing scope boundary.

### System

A system groups components (or sub-systems) that work toward a shared goal. Systems declare **channels** that wire their members together without naming specific pairs. Systems may contain components and other systems, but components may not contain systems.

```
system ECommerce {
    title = "E-Commerce Platform"
    description = "Customer-facing online store."

    channel payment: PaymentRequest {
        protocol = "gRPC"
        async = true
    }
    channel inventory: InventoryCheck {
        protocol = "HTTP"
    }

    component OrderService {
        requires PaymentRequest via payment
        requires InventoryCheck via inventory
        provides OrderConfirmation
    }

    component PaymentGateway {
        provides PaymentRequest via payment
    }

    component InventoryManager {
        requires InventoryCheck via inventory
        provides InventoryStatus
    }
}
```

Systems can nest other systems for large-scale decomposition:

```
system Enterprise {
    title = "Enterprise Landscape"

    channel inventory: InventorySync

    system ECommerce {
        provides InventorySync via inventory
    }

    system Warehouse {
        requires InventorySync via inventory
    }
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

Users are leaf nodes — they cannot contain components or sub-users. A user participates in channels like any other entity:

```
system ECommerce {
    channel order_in: OrderRequest
    channel order_out: OrderConfirmation

    user Customer {
        provides OrderRequest via order_in
        requires OrderConfirmation via order_out
    }

    component OrderService {
        requires OrderRequest via order_in
        provides OrderConfirmation via order_out
    }
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

## Channels

A **channel** is a named conduit that carries a specific interface within a system or component scope. Channels decouple providers from requirers: each component binds to a channel by name without knowing who else is bound to it.

### Channel declaration

Channels are declared inside a system or component body:

```
channel <name>: <Interface> [@version] [{ attributes }]
```

```
channel payment: PaymentRequest
channel feed: DataFeed @v2 {
    protocol = "gRPC"
    async = true
    description = "Asynchronous data feed channel."
}
```

Channel attributes (each on its own line):

| Attribute     | Type    | Purpose                                    |
| ------------- | ------- | ------------------------------------------ |
| `protocol`    | string  | Transport protocol (e.g. `"gRPC"`, `"HTTP"`) |
| `async`       | boolean | Whether the channel is asynchronous        |
| `description` | string  | Human-readable explanation of the channel  |

### Binding to a channel

A `requires` or `provides` declaration binds to a channel with the `via` keyword:

```
requires <Interface> [@version] via <channel>
provides <Interface> [@version] via <channel>
```

```
component OrderService {
    requires PaymentRequest via payment       // binds to the "payment" channel
    requires InventoryCheck via inventory     // binds to the "inventory" channel
    provides OrderConfirmation                // unbound — visible at the enclosing scope
}
```

The `via` clause is optional. An unbound interface declaration is still valid — it represents an interface the entity exposes at its boundary for the enclosing scope to wire.

The tooling validates that:
- The channel name in `via` is declared in the same scope (system or component body).
- The interface type of the binding matches the channel's declared interface type.
- Channel names are unique within their scope.

### Encapsulation

A channel declared inside a component is local to that component — it is not visible from outside. Components without `via` bindings expose their unbound `requires`/`provides` declarations at the enclosing boundary.

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

    channel order_in: OrderRequest
    channel order_out: OrderConfirmation

    use component OrderService
}
```

The `use` keyword only places an already-imported entity; it does not allow overriding fields or interfaces.

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
from types import OrderItem, OrderRequest, ValidationResult, PaymentRequest, InventoryCheck, OrderConfirmation

component OrderService {
    title = "Order Service"
    description = "Accepts, validates, and processes customer orders."

    channel validation: ValidationResult

    component Validator {
        title = "Order Validator"

        requires OrderRequest
        provides ValidationResult via validation
    }

    component Processor {
        title = "Order Processor"

        requires ValidationResult via validation
        requires PaymentRequest
        requires InventoryCheck
        provides OrderConfirmation
    }
}

// file: systems/ecommerce.archml
from types import OrderRequest, OrderConfirmation, PaymentRequest, PaymentResult, InventoryCheck, InventoryStatus
from components/order_service import OrderService

user Customer {
    title = "Customer"
    description = "An end user who places orders through the e-commerce platform."

    provides OrderRequest
    requires OrderConfirmation
}

external system StripeAPI {
    title = "Stripe Payment API"
    requires PaymentRequest
    provides PaymentResult
}

system ECommerce {
    title = "E-Commerce Platform"

    channel order_in: OrderRequest
    channel order_out: OrderConfirmation
    channel payment: PaymentRequest {
        protocol = "gRPC"
        async = true
        description = "Delegate payment processing."
    }
    channel inventory: InventoryCheck {
        protocol = "HTTP"
    }

    user Customer {
        provides OrderRequest via order_in
        requires OrderConfirmation via order_out
    }

    use component OrderService

    component PaymentGateway {
        title = "Payment Gateway"
        tags = ["critical", "pci-scope"]

        requires PaymentRequest via payment
        provides PaymentResult
    }

    component InventoryManager {
        title = "Inventory Manager"

        requires InventoryCheck via inventory
        provides InventoryStatus
    }
}
```

## Summary of Keywords

| Keyword         | Purpose                                                                                                            |
| --------------- | ------------------------------------------------------------------------------------------------------------------ |
| `system`        | Group of components or sub-systems with a shared goal.                                                             |
| `component`     | Module with a clear responsibility; may nest sub-components.                                                       |
| `user`          | Human actor (role or persona) that interacts with the system; a leaf node.                                         |
| `interface`     | Named contract of typed data fields. Supports versioning via `@v1`, `@v2`, etc.                                    |
| `channel`       | Named conduit that carries a specific interface within a system or component scope.                                 |
| `type`          | Reusable data structure (used within interfaces).                                                                  |
| `enum`          | Constrained set of named values.                                                                                   |
| `field`         | Named, typed data element. Supports `description` and `schema` annotations.                                        |
| `filetype`      | Annotation on a `File` field specifying its format.                                                                |
| `schema`        | Free-text annotation describing expected content or format.                                                        |
| `requires`      | Declares an interface an element consumes (listed before `provides`).                                              |
| `provides`      | Declares an interface an element exposes.                                                                          |
| `via`           | Binds a `requires` or `provides` declaration to a named channel (`requires X via channel`).                        |
| `from`          | Introduces the source path in an import statement (`from path import Name`).                                       |
| `import`        | Names the specific entities to bring into scope; always paired with `from` (`from path import Name`).              |
| `use`           | Places an imported entity into a system or component (e.g., `use component X`).                                    |
| `external`      | Marks a system, component, or user as outside the development boundary.                                            |
| `tags`          | Arbitrary labels for filtering and view generation.                                                                |
| `title`         | Human-readable display name.                                                                                       |
| `description`   | Longer explanation of an entity's purpose.                                                                         |

## Scope Boundaries

- **Views** are not part of the architecture language syntax. They are defined in a separate view DSL that references entities from the architecture model.
