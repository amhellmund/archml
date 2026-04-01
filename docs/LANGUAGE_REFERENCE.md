# ArchML Language Reference

ArchML is a text-based DSL for defining software architecture alongside code. Architecture files use the `.archml` extension.

---

## File Structure

A file contains one or more top-level declarations. Declarations can be nested to express containment.

```
# Line comments start with a hash sign.
```

**Identifiers** are unquoted alphanumeric names that may contain underscores or dashes (`order_service`, `order-service`).

**Descriptions** are triple-quoted Markdown strings at the top of any entity body, before any attributes or declarations:

```
component OrderService {
    """
    Accepts and validates customer orders.

    See [ADR-12](docs/adr/0012-order-flow.md) for the design rationale.
    """

    requires PaymentRequest
    provides OrderConfirmation
}
```

**Custom Attributes** attach metadata to any entity using the `@name: values` syntax. Values are comma-separated identifiers (no strings, no spaces within values). Attributes are user-defined; the tooling does not interpret them — they can express tags, ownership, or any other domain-specific classification.

```
component OrderService {
    @team: platform
    @tags: critical, payments

    requires PaymentRequest
    provides OrderConfirmation
}
```

Multiple values on a single `@` line form a set. An entity may have any number of `@` attributes.

---

## Type System

### Primitive Types

| Type        | Description              |
| ----------- | ------------------------ |
| `String`    | Unicode string           |
| `Int`       | Integer number           |
| `Float`     | Floating-point number    |
| `Bool`      | Boolean value            |
| `Bytes`     | Raw byte sequence        |
| `Timestamp` | Point in time (epoch)    |
| `Datetime`  | Calendar date and time   |

### Container Types

| Type          | Description                    |
| ------------- | ------------------------------ |
| `List<T>`     | Ordered sequence of `T`        |
| `Map<K, V>`   | Key–value mapping              |
| `Optional<T>` | Value that may be absent       |

### Enumerations

The `enum` keyword defines a constrained set of named values. Each value appears on its own line:

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

The `type` keyword defines a reusable data structure. Fields use `name: Type` syntax, one per line:

```
type OrderItem {
    product_id: String
    quantity:   Int
    unit_price: Float
}
```

Custom types, enums, and interfaces can all be used as field types.

---

## Core Entities

### Interface

An interface defines a contract — a named set of typed fields exchanged between architectural elements. Interfaces are declared at the top level or inside components and systems. Fields use `name: Type` syntax, one per line:

```
interface OrderRequest {
    """Payload for submitting a new customer order."""

    order_id:    String
    customer_id: String
    items:       List<OrderItem>
    currency:    String
}
```

`interface` defines contracts used on ports. `type` defines building blocks composed into fields. The distinction is semantic: interfaces appear on ports; types compose into fields.

### Component

A component is a module with a clear responsibility. Components declare the interfaces they consume (`requires`) and produce (`provides`) as **ports**.

```
component OrderService {
    requires PaymentRequest
    requires InventoryCheck
    provides OrderConfirmation
}
```

Components can nest sub-components. `connect` statements wire sub-components together. Every port of every sub-component must either be wired by a `connect` or promoted to the enclosing boundary with `expose`:

```
component OrderService {

    component Validator {
        requires OrderRequest
        provides ValidationResult
    }

    component Processor {
        requires ValidationResult
        requires PaymentRequest
        provides OrderConfirmation
    }

    connect Validator.ValidationResult -> $validation -> Processor.ValidationResult

    expose Validator.OrderRequest
    expose Processor.PaymentRequest
    expose Processor.OrderConfirmation
}
```

A port that is neither wired nor exposed is a validation error. Components may not contain systems.

### System

A system groups components (or sub-systems) that work toward a shared goal. Systems wire their members using `connect` and `expose`. Systems may nest other systems for large-scale decomposition:

```
system Enterprise {

    system ECommerce {
        provides InventorySync
    }

    system Warehouse {
        requires InventorySync
    }

    connect ECommerce.InventorySync -> $inventory_sync -> Warehouse.InventorySync
}
```

### User

A user represents a human actor — a role or persona that interacts with the system. Users are leaf nodes; they cannot contain sub-entities.

```
user Customer {
    """An end user who places orders through the e-commerce platform."""

    provides OrderRequest
    requires OrderConfirmation
}
```

Users participate in `connect` statements like any other entity.

---

## Data Flow Statements

### Ports: `requires` and `provides`

Every `requires` and `provides` declaration defines a **port** — a named connection point on the entity. The port name defaults to the interface name; use `as` to assign an explicit name:

```
requires <Interface> [as <port_name>]
provides <Interface> [as <port_name>]
```

`requires` declarations appear before `provides`. Port names must be unique within their entity.

### Channels and `connect`

A **channel** is a named conduit between ports. Channels are introduced implicitly by `connect` statements — there is no separate channel declaration. Channel names use the `$` prefix to distinguish them from ports.

`connect` statements can appear inside `component` or `system` bodies, or at the top level of an `.archml` file to wire top-level entities.

```
// Full chain: introduces $channel and wires both ports
connect <src_port> -> $<channel> -> <dst_port>

// One-sided: introduces or references $channel, wires one port
connect <src_port> -> $<channel>
connect $<channel> -> <dst_port>
```

`<src_port>` and `<dst_port>` are either:

- `Entity.port_name` — explicit port on a named child entity

The arrow direction follows data flow: a `provides` port (producer) is always on the left; a `requires` port (consumer) is always on the right.

A channel introduced by `connect` is local to the scope where it appears — it is not visible outside.

### Port Exposure: `expose`

`expose` promotes a sub-entity's port to the enclosing boundary. A port that is neither wired by `connect` nor promoted by `expose` is a validation error.

```
expose Entity.port_name [as new_name]
```

The port name must always be specified (e.g., `Entity.port_name`); implicit port inference is not supported. The optional `as` clause renames the port at the boundary. `expose` composes across levels — a system can expose a port that was already exposed by an inner component.

---

## Variant Handling

Variants model multiple architectural possibilities within a single file. Each named variant represents a distinct configuration (e.g., `cloud` vs. `on_premise`, or `current` vs. `target`).

Variants are **global** across the entire build. Variant names are declared implicitly by use; no explicit top-level declaration is required.

### Inline Variant Annotation

Any entity or statement accepts an optional `<variant, ...>` annotation immediately after its keyword:

```
system<cloud> ECommerce { ... }
component<cloud, hybrid> AuditLogger { ... }
requires<cloud> StripeWebhook
connect<cloud> PaymentGateway.PaymentRequest -> $payment -> OrderService.PaymentRequest
expose<on_premise> Processor.PaymentRequest
interface<cloud> CloudPaymentRequest { ... }
```

**Block-level entities** (`system`, `component`, `user`): the annotation marks the entity itself and **propagates to all children**. Children inherit the enclosing entity's variant set; their own annotation extends it.

**Statements** (`requires`, `provides`, `connect`, `expose`): the annotation marks only that statement.

### Union Semantics

The effective variant set of an entity is the **union** of:

- Variants inherited from enclosing block-level entities.
- Variants in the entity's own `<>` annotation.

An entity with no annotation and no enclosing annotation is **baseline** — present in every variant.

```
system<cloud> ECommerce {
    component OrderService {}         # effective set: {cloud}
    component<hybrid> AuditLogger {}  # effective set: {cloud, hybrid}
}
```

`AuditLogger` is present when both `cloud` and `hybrid` are active. `OrderService` is present in any `cloud` configuration. Baseline entities have no annotation and are present in all configurations.

### Validation per Variant

All consistency checks (port coverage, dangling references, unused interfaces) are evaluated independently for each declared variant. A port wired in only one variant must be wired or exposed in every variant in which its owning entity appears.

---

## External Systems

The `external` modifier marks systems, components, or users that are outside the development boundary. External entities appear in diagrams with distinct styling and cannot be decomposed (they are opaque):

```
external system StripeAPI {
    requires PaymentRequest
    provides PaymentResult
}

external user Admin {
    provides AdminCommand
}
```

`external` applies to `system`, `component`, and `user`.

---

## Multi-File Composition

Large architectures are split across files. Top-level declarations (`component`, `system`, `user`, `interface`, `type`, `enum`) can appear in any `.archml` file — they do not need to be nested inside a system.

### Imports

`from ... import` brings named definitions from another file into scope:

```
from dir/subdir/file import Entity
from dir/subdir/file import Entity1, Entity2
```

The path omits the `.archml` extension and is resolved using the repository's virtual filesystem mapping (see [Repository Configuration](#repository-configuration)).

### `use`

The `use` keyword places an already-imported entity into a system or component body without redefining it. Always includes the entity type:

```
use component OrderService
use system ECommerce
use user Customer
```

The entity's exposed ports become available as `Entity.port_name` targets in `connect` and `expose` statements within the enclosing scope.

### Cross-Repository Imports

To import from another repository, prefix the path with `@repo-name`:

```
from @payments/services/payment import PaymentService
from @inventory/services/stock  import StockManager
```

`@repo-name` refers to a named repository declared in the workspace configuration. When the `@` prefix is omitted, the current repository is assumed.

---

## Repository Configuration

Each repository declares a virtual filesystem mapping in `archml.yaml` at the repository root. The mapping assigns short names to paths relative to the repository root:

```yaml
# archml.yaml
roots:
  interfaces: src/architecture/interfaces
  components:  src/architecture/components
  systems:     src/architecture/systems
  types:       src/architecture/types
```

An import path is resolved by matching its first segment against declared root names. For example, `interfaces/order` resolves to `src/architecture/interfaces/order.archml`. A path whose first segment matches no declared root is a resolution error. Roots can map to individual files as well as directories.

---

## Workspace Configuration

Cross-repository imports require `archml-workspace.yaml` at the workspace root:

```yaml
# archml-workspace.yaml
name: my-workspace
build-directory: .archml-build
source-imports:
  - name: payments
    git: https://github.com/example/payments-service
    ref: main
  - name: inventory
    git: https://github.com/example/inventory-service
    ref: v2.3.0
```

The `name` under `source-imports` matches the `@repo-name` prefix in import paths. `ref` pins the import to a specific branch, tag, or commit.

---

## Keyword Reference

| Keyword       | Purpose                                                                                  |
| ------------- | ---------------------------------------------------------------------------------------- |
| `system`      | Group of components or sub-systems with a shared goal.                                   |
| `component`   | Module with a clear responsibility; may nest sub-components.                             |
| `user`        | Human actor (role or persona); leaf node — cannot contain sub-entities.                  |
| `interface`   | Named contract of typed fields used on ports.                                            |
| `type`        | Reusable data structure composed into interface fields.                                  |
| `enum`        | Constrained set of named values.                                                         |
| `requires`    | Declares a port that consumes an interface.                                              |
| `provides`    | Declares a port that produces an interface.                                              |
| `as`          | Assigns an explicit name to a port (`requires PaymentRequest as pay_in`).                |
| `connect`     | Wires ports, optionally via a named channel (`connect A.p -> $ch -> B.p`).               |
| `expose`      | Promotes a sub-entity's port to the enclosing boundary (`expose Entity.port [as name]`). |
| `$channel`    | Channel name in `connect`; `$` prefix distinguishes channels from ports.                 |
| `from`        | Source path in an import statement (`from path import Name`).                            |
| `import`      | Entities to bring into scope; always paired with `from`.                                 |
| `use`         | Places an imported entity into a system or component (`use component X`).                |
| `external`    | Marks a system, component, or user as outside the development boundary.                  |
| `<v1, v2>`   | Variant annotation on an entity or statement.                                            |
| `@attr: ...`  | Custom attribute on an entity; values are comma-separated identifiers.                   |
| `"""..."""`   | Markdown description at the top of any entity body.                                      |