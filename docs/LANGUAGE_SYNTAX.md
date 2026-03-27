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

Identifiers are unquoted alphanumeric names with underscores (e.g., `order_service`). Every named entity has an optional `description`.

Multi-line text is written with triple-quoted strings (`"""`):

```
description = """
Accepts and validates customer orders.
Delegates payment processing to the PaymentGateway
and inventory checks to the InventoryManager.
"""
```

## Type System

### Primitive Types

`String`, `Int`, `Float`, `Bool`, `Bytes`, `Timestamp`, `Datetime`

### Artifacts

The `artifact` keyword defines an abstract, named data artifact — a file, directory, stream, blob, or any other data shape exchanged between components. The concrete implementation (which filesystem type, storage backend, etc.) is specified in the deployment architecture. Artifacts can be used as field types within `type` and `interface` definitions.

```
artifact MonthlyReport {
    description = "PDF summary of monthly sales figures per region."
    spec = "Single-page PDF, A4, landscape. Header contains logo and date range."
    ref_url = "https://internal.wiki/report-format"
}
```

| Attribute     | Required | Description                                                      |
| ------------- | -------- | ---------------------------------------------------------------- |
| `description` | no       | Purpose and context of the artifact.                             |
| `spec`        | no       | Free-text description of the expected content, shape, or format. |
| `ref_url`     | no       | URL to an external specification or reference document.          |

Once defined, an artifact is referenced by name as a field type in any `type` or `interface`:

```
interface ReportOutput {
    report: MonthlyReport
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
    product_id: String
    quantity: Int
    unit_price: Float
}
```

Custom types, enums, and interfaces can all be referenced by name as field types.

## Core Entities

### Interface

An interface defines a contract — a named set of typed data fields exchanged between architectural elements. Interfaces are declared at the top level or inside components and systems.

```
interface OrderRequest {
    """Payload for submitting a new customer order."""

    order_id: String
    customer_id: String
    items: List<OrderItem>
    total_amount: Float
    currency: String
}
```

`interface` defines a contract used on ports. `type` defines a building block used within interfaces. Both share the same field syntax (`name: type`, one per line) — the distinction is semantic: interfaces appear on ports; types compose into fields.

### Component

A component is a module with a clear responsibility. Components declare the interfaces they **require** (consume) and **provide** (expose) as **ports**. `requires` declarations always come before `provides`.

```
component OrderService {
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

    component Validator {
    
        requires OrderRequest
        provides ValidationResult
    }

    component Processor {
    
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

    connect PaymentGateway.PaymentRequest -> $payment -> OrderService.PaymentRequest
    connect InventoryManager.InventoryCheck -> $inventory -> OrderService.InventoryCheck

    // OrderService.OrderConfirmation has no internal consumer — expose it as the
    // system's own boundary port
    expose OrderService.OrderConfirmation
}
```

Systems can nest other systems for large-scale decomposition:

```
system Enterprise {

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
    requires PaymentRequest
    provides PaymentResult
}

external user Admin {
    provides AdminCommand
}
```

External entities appear in diagrams with distinct styling. They cannot be further decomposed (they are opaque).

## Ports and Channels

### Ports

Every `requires` and `provides` declaration defines a **port** — a named connection point on the entity. The port name defaults to the interface name; use `as` to assign an explicit name:

```
requires <Interface> [as <port_name>]
provides <Interface> [as <port_name>]
```

```
requires PaymentRequest                   // port named "PaymentRequest"
requires PaymentRequest as pay_in         // port named "pay_in"
provides OrderConfirmation as confirmed   // port named "confirmed"
```

Port names must be unique within their entity. When two sub-entities have ports with the same name and both are promoted via `expose`, use `as` to disambiguate.

### Channels and the `connect` Statement

A **channel** is a named conduit between ports. Channels are introduced implicitly by `connect` statements — there is no separate channel declaration. Channel names use the `$` prefix to distinguish them from port names.

`connect` statements can appear inside a `component` or `system` body, **or at the top level of an `.archml` file** to wire high-level systems to each other.

The `connect` statement supports two port reference styles:

- **Full form** — `Entity.port_name`: explicit entity and port name.
- **Simplified form** — `Entity`: bare entity name with automatic port inference. Valid when the entity has exactly one `provides` port (for the sender side) or exactly one `requires` port (for the receiver side). The tooling infers the port and reports an error if the port is ambiguous.

```
// Full chain: introduces $channel and wires both ports in one statement
connect <src_port> -> $<channel> -> <dst_port>

// One-sided: introduces or references $channel, wires one port
connect <src_port> -> $<channel>
connect $<channel> -> <dst_port>
```

`<src_port>` and `<dst_port>` are either:

- `Entity.port_name` — explicit port on a named child entity (full form)
- `Entity` — child entity with a single unambiguous port (simplified form)
- `port_name` — a port on the current scope's own boundary

The arrow direction follows data flow: a `provides` port (producer) is always on the left; a `requires` port (consumer) is always on the right.

```
// Full chain — explicit Entity.port notation
connect PaymentGateway.PaymentRequest -> $payment -> OrderService.PaymentRequest

// Simplified form — port inferred automatically (each entity has one matching port)
connect PaymentGateway -> $payment -> OrderService

// Multi-step — build up a channel across two statements (same result)
connect PaymentGateway.PaymentRequest -> $payment
connect $payment -> OrderService.PaymentRequest

// Top-level connect — wires two top-level systems across file scope
connect Frontend.API -> $bus -> Backend.API
```

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

## Variants

Variants model multiple architectural possibilities within a single file. Each named variant represents a distinct configuration — for example, a cloud deployment vs. an on-premise deployment, or the current state vs. a target state. Tooling can render or validate the architecture for a specific active variant.

Variants are **global** across the entire build — the same name used in different files refers to the same variant. Variant names are declared implicitly by using them; no explicit top-level declaration is required.

### Baseline Entities

Any entity that carries no variant annotation is **baseline** — it is present in every variant. Baseline entities form the shared core of the architecture.

### Inline Variant Annotation

Any entity or statement accepts an optional `<variant, ...>` annotation immediately after its keyword. The annotation lists the variants the entity or statement belongs to.

**Block-level entities** (`system`, `component`, `user`): the annotation marks the entity itself and **propagates to all children**. Children inherit the enclosing entity's variant set and can extend it with their own annotation.

```
system<cloud> ECommerce {
    component OrderService {}         # effective set: {cloud} (inherited)
    component<hybrid> AuditLogger {}  # effective set: {cloud, hybrid}
}
```

**Statements** (`connect`, `expose`, `requires`, `provides`): the annotation marks only that statement.

```
component OrderService {
    requires PaymentRequest           # baseline — always present
    requires<cloud> StripeWebhook     # only in the cloud variant
    provides OrderConfirmation
}

connect<cloud> PaymentGateway.PaymentRequest -> $payment -> OrderService.PaymentRequest
expose<on_premise> Processor.PaymentRequest
```

### `variant` Blocks

For grouping multiple declarations under shared variants, use a `variant<A, B> { ... }` block inside a `system` or `component` body. All declarations inside the block inherit the block's variants:

```
system ECommerce {
    component OrderService {}             # baseline

    variant<cloud, hybrid> {
        component PaymentGateway {
            provides PaymentRequest
        }

        connect PaymentGateway.PaymentRequest -> $payment -> OrderService.PaymentRequest
    }

    variant<on_premise> {
        component LocalPaymentProcessor {
            provides PaymentRequest
        }

        connect LocalPaymentProcessor.PaymentRequest -> $payment -> OrderService.PaymentRequest
    }

    expose OrderService.OrderConfirmation
}
```

A `variant` block can name multiple variants, which is useful when a group of declarations belongs to more than one variant without duplicating the block.

### Union Semantics

The effective variant set of an entity is the **union** of:

- Variants inherited from any enclosing block-level entities (`system<>`, `component<>`, `user<>`).
- Variants inherited from any enclosing `variant<>` blocks.
- Variants in the entity's own `<>` annotation.

An entity with no annotation and no enclosing annotation source is baseline. Variants are orthogonal tags, not mutually exclusive alternatives — `{cloud, hybrid}` means the entity is present when both tags are active simultaneously. The mechanisms compose freely at any nesting depth:

```
system<cloud> ABC {
    component CDE {}              # effective set: {cloud} (inherited)
    component<hybrid> XYZ {}      # effective set: {cloud, hybrid}
}
```

Here `XYZ` is present in configurations where both `cloud` and `hybrid` are active, while `CDE` is present in any `cloud` configuration.

### Validation per Variant

All consistency checks — port coverage, dangling references, unused interfaces — are evaluated independently for each declared variant. A port that is only wired in one variant must be wired or exposed in every variant in which its owning entity appears.

### Variants and Imported Entities

Because variants are global, variant annotations on imported entities are directly meaningful in the importing scope — no re-declaration or mapping is needed. The importing scope can use `variant<>` blocks or inline annotations to make the inclusion of an entity conditional:

```
system Enterprise {
    use component OrderService          # baseline — present in every variant

    variant<cloud> {
        use component CloudAuditLogger
        connect CloudAuditLogger -> $audit -> OrderService
    }
}
```

## Multi-File Composition

Large architectures are split across files. The `from ... import` statement brings specific named definitions from other files into scope. The `use` keyword places an imported entity into a system or parent component without redefining it. `use` always includes the entity type for clarity (`use component`, `use system`, `use user`).

Components, systems, users, interfaces, types, and enums can all be defined at the top level of any `.archml` file — they do not need to be nested inside a system. This enables a one-file-per-entity workflow where each entity is self-contained and systems compose them by reference.

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

    requires OrderRequest
    provides OrderConfirmation
}

// file: systems/ecommerce.archml
from interfaces/order import OrderRequest, OrderConfirmation, PaymentRequest, InventoryCheck
from components/order_service import OrderService

system ECommerce {

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

    use component OrderService
    use component PaymentService
    use component StockManager
    use user Customer
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
    product_id: String
    quantity: Int
    unit_price: Float
}

enum OrderStatus {
    Pending
    Confirmed
    Shipped
    Delivered
    Cancelled
}

interface OrderRequest {
    order_id: String
    customer_id: String
    items: List<OrderItem>
}

interface OrderConfirmation {
    order_id: String
    status: OrderStatus
    confirmed_at: Timestamp
}

interface PaymentRequest {
    order_id: String
    amount: Float
    currency: String
}

interface PaymentResult {
    order_id: String
    success: Bool
    transaction_id: Optional<String>
}

interface InventoryCheck {
    product_id: String
    quantity: Int
}

interface InventoryStatus {
    product_id: String
    available: Bool
}

interface ValidationResult {
    order_id: String
    valid: Bool
}

artifact MonthlyReport {
    spec = "Monthly sales summary PDF."
}

interface ReportOutput {
    report: MonthlyReport
}

// file: components/order_service.archml
from types import OrderRequest, ValidationResult, PaymentRequest, InventoryCheck, OrderConfirmation

component OrderService {
    description = "Accepts, validates, and processes customer orders."

    component Validator {
    
        requires OrderRequest
        provides ValidationResult
    }

    component Processor {
    
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

    user Customer {
            description = "An end user who places orders through the e-commerce platform."

        provides OrderRequest
        requires OrderConfirmation
    }

    use component OrderService

    component PaymentGateway {
        
        provides PaymentRequest
        requires PaymentResult
    }

    component InventoryManager {
    
        provides InventoryCheck
    }

    external system StripeAPI {
            requires PaymentRequest
        provides PaymentResult
    }

    // Wire Customer to OrderService
    connect Customer.OrderRequest -> $order_in -> OrderService.OrderRequest
    connect OrderService.OrderConfirmation -> $order_out -> Customer.OrderConfirmation

    // Wire OrderService to backing services
    connect PaymentGateway.PaymentRequest -> $payment -> OrderService.PaymentRequest
    connect InventoryManager.InventoryCheck -> $inventory -> OrderService.InventoryCheck

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
| `interface`     | Named contract of typed data fields used on ports.                                                                 |
| `type`          | Reusable data structure (used within interfaces).                                                                  |
| `enum`          | Constrained set of named values.                                                                                   |
| `artifact`      | Abstract data artifact (file, directory, blob, etc.) whose concrete form is given in the deployment architecture.  |
| `spec`          | Free-text annotation on an `artifact` describing its expected content, shape, or format.                           |
| `ref_url`       | Optional URL on an `artifact` pointing to an external specification.                                               |
| `requires`      | Declares a port that consumes an interface (listed before `provides`).                                             |
| `provides`      | Declares a port that exposes an interface.                                                                         |
| `as`            | Assigns an explicit name to a port (`requires PaymentRequest as pay_in`).                                          |
| `connect`       | Wires ports together, optionally via a named channel (`connect A.p -> $ch -> B.p`).                                |
| `expose`        | Explicitly surfaces a sub-entity's port at the enclosing boundary (`expose Entity.port [as name]`).               |
| `$channel`      | Channel name in a `connect` statement; `$` prefix distinguishes channels from ports.                               |
| `from`          | Introduces the source path in an import statement (`from path import Name`).                                       |
| `import`        | Names the specific entities to bring into scope; always paired with `from` (`from path import Name`).              |
| `use`           | Places an imported entity into a system or component (e.g., `use component X`, `use system X`, `use user X`).      |
| `external`      | Marks a system, component, or user as outside the development boundary.                                            |
| `variant`       | Opens a variant block inside a `system` or `component` body that conditionally includes its contents (`variant<cloud> { ... }`). |
| `description`   | Longer explanation of an entity's purpose.                                                                         |

## Scope Boundaries

- **Views** are not part of the architecture language syntax. They are defined in a separate view DSL that references entities from the architecture model.
