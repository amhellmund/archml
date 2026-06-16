# ArchML

ArchML is a text-based DSL for defining software architecture next to your code.
Architecture files use the `.farchml` extension, live in the repository, are version-controlled like any other source file, and stay in sync with the system they describe.

The core idea: define your architecture once as a model, then derive multiple views from it — interactive web diagrams, consistency reports, and embedded Sphinx documentation — without maintaining separate diagrams per tool.

## Why ArchML?

Architecture documentation drifts.
Visual tools like Enterprise Architect or ArchiMate live outside the codebase, so diagrams rot while the code moves on.
Lightweight alternatives like Mermaid embed diagrams in Markdown, but each diagram is standalone — there is no shared model, no cross-diagram consistency, and no drill-down navigation.

ArchML sits between these extremes:

- **Text-first** — `.farchml` files are plain text, stored in git, reviewed in pull requests.
- **Model-based** — one model, many views. Define a component once; reference it everywhere.
- **Consistency checking** — the tooling catches dangling references, ports missing `connect` or `expose`, and type mismatches across channels.
- **Navigable views** — drill down from system landscape to individual component internals.
- **Sphinx-native** — embed live architecture views directly in your documentation.

Three architecture domains are covered: **functional** (systems, components, interfaces — implemented), **behavioral** (control flow, sequences — planned), and **deployment** (infrastructure mapping — planned).

## Quick Example

A small e-commerce backend expressed in ArchML.
The example shows the core principles: shared interfaces, a composite component with internal wiring, a user actor, and custom metadata attributes.

```
# types.farchml — shared data contracts

type OrderItem {
    product_id: String
    quantity: Int
    unit_price: Float
}

enum OrderStatus { 
    Pending
    Confirmed
    Shipped
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
```

```
# systems/ecommerce.farchml

from types import OrderRequest, OrderConfirmation, PaymentRequest

system ECommerce {
    """Customer-facing online store."""

    # Declared channels — every $name used in connect must be declared here
    channel order_in:  OrderRequest
    channel order_out: OrderConfirmation
    channel payment:   PaymentRequest

    # Human actor — same port model as components
    user Customer {
        requires OrderConfirmation
        provides OrderRequest
    }

    # Composite component: internal structure is hidden behind exposed ports
    component OrderService {
        """Accepts, validates, and processes customer orders."""

        @team: platform
        @tags: critical, orders

        # Channel declared at component scope — local to this component
        channel validation: ValidationResult

        component Validator {
            requires OrderRequest
            provides ValidationResult
        }

        component Processor {
            requires ValidationResult
            requires PaymentRequest
            provides OrderConfirmation
        }

        # Wire Validator output to Processor input via the declared channel
        connect Validator.ValidationResult -> $validation -> Processor.ValidationResult

        # Remaining ports are promoted to the OrderService boundary
        expose Validator.OrderRequest
        expose Processor.PaymentRequest
        expose Processor.OrderConfirmation
    }

    component PaymentGateway {
        @tags: pci-scope
        provides PaymentRequest
    }

    # Wire customer to order pipeline
    connect Customer.OrderRequest            -> $order_in  -> OrderService.OrderRequest
    connect OrderService.OrderConfirmation   -> $order_out -> Customer.OrderConfirmation

    # Wire OrderService to backing services
    connect PaymentGateway.PaymentRequest    -> $payment   -> OrderService.PaymentRequest
}
```

**What this demonstrates:**

- **Interfaces and types** — `type` defines building blocks; `interface` defines port contracts. Fields use `name: Type` syntax.
- **Ports** — `requires` and `provides` declare connection points. Port names default to the interface name; `as` assigns an explicit alias.
- **Declared channels** — every `$name` used in `connect` must be declared as `channel name: Interface` in the same scope. The declaration binds a name to a contract type; the tooling validates that both connected ports carry that interface.
- **Exposure** — `expose` promotes a sub-component's port to the enclosing boundary. Every sub-component port must be either wired or exposed — the tooling reports a validation error otherwise.
- **User actors** — `user` is a leaf node with the same port model as components.
- **Custom attributes** — `@team: platform` and `@tags: critical, pci-scope` attach user-defined metadata.
- Values are comma-separated identifiers; the tooling does not interpret them.

Large architectures split across files with `from ... import`.
`use component X` instantiates a definition inside a system: the instance carries the
definition's real ports and internal structure, and its open ports must be wired by the
host. A `template system/component/user` is a reusable blueprint that is never rendered on
its own — it appears only where it is instantiated with `use`.
Remote repositories are referenced with `@repo-name` prefixes for multi-repo workspaces.
Variants (`<cloud, on_premise>`) model multiple configurations within a single file.
`config DbConfig` declares an external configuration dependency resolved by the deployment layer.

## Language at a Glance

| Keyword / Syntax               | Purpose                                                                 |
| ------------------------------ | ----------------------------------------------------------------------- |
| `system`                       | Group of components or sub-systems with a shared goal                   |
| `component`                    | Module with a clear responsibility; may nest sub-components             |
| `user`                         | Human actor (role or persona); leaf node                                |
| `interface`                    | Named contract of typed fields used on ports                            |
| `type`                         | Reusable data structure composed into interface fields                  |
| `enum`                         | Constrained set of named values                                         |
| `channel Name: Type`           | Declare a named, typed channel; required before any `$Name` in connect  |
| `requires` / `provides`        | Declare a port that consumes or exposes an interface                    |
| `requires X as port`           | Assign an explicit name to a port                                       |
| `config TypeName [as name]`    | Declare an external configuration dependency (resolved by deployment)   |
| `connect A.p -> $ch -> B.p`    | Wire two ports via a declared channel                                   |
| `expose Entity.port [as name]` | Promote a sub-entity's port to the enclosing boundary                  |
| `template`                     | Reusable blueprint, never rendered standalone; only used via `use`      |
| `external`                     | Marks a system, component, or user as outside the development boundary  |
| `<v1, v2>`                     | Variant annotation on an entity or statement                            |
| `@attr: val1, val2`            | Custom attribute; values are comma-separated identifiers                |
| `from … import`                | Bring definitions from another file into scope                          |
| `use component/system/user X`  | Instantiate a definition (with its real ports) inside a system          |

Primitive types: `String`, `Int`, `Float`, `Bool`, `Bytes`, `Timestamp`, `Datetime`
Container types: `List<T>`, `Map<K, V>`, `Optional<T>`
Reference types: `Url<Schema>` — a typed pointer to a resource shaped like `Schema` (a `type` or `interface`); the scheme and location are runtime values, only the schema is part of the contract

Full language reference: [docs/language_specs/functional_architecture.md](docs/language_specs/functional_architecture.md)

## Installation

```bash
pip install archml
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add archml
```

## Commands

### `archml init <name> <directory>`

Initialize a new ArchML workspace.
Creates `.archml-workspace.yaml` in the given directory with `<name>` as the workspace identity.

```bash
archml init my-service .
```

---

### `archml check [-C <directory>]`

Parse and validate all `.farchml` files in the workspace.
Instantiates every `use` (and template), then reports dangling references, unwired ports,
disconnected entities, type definition cycles, instantiation cycles, and template warnings
(unused or nested templates).
Exits with a non-zero status if any errors are found.

```bash
archml check
archml check -C /path/to/workspace
```

---

### `archml visualize <entity> <output> [-C <directory>]`

Render a box diagram for a system or component and write it to a file.
The entity path uses `::` as a separator for nested elements.
Use `all` as the entity to render every top-level entity in a single diagram.

```bash
archml visualize ECommerce diagram.svg
archml visualize ECommerce::OrderService order_service.svg
archml visualize all landscape.svg --depth 1
archml visualize ECommerce diagram.svg --variant cloud
```

---

### `archml export [-C <directory>] [-o <file>]`

Generates a self-contained HTML file with the interactive architecture viewer.
Supports drill-down navigation across all entities in the workspace.

```bash
archml export
archml export -o architecture.html
archml export -C /path/to/workspace -o viewer.html
```

---

### `archml update-remote [-C <directory>]`

Resolve the full transitive graph of remote git imports, pinning each branch or tag reference to a commit SHA, and write the resulting closure to the lockfile (`.farchml-lockfile.yaml`).
Fails with a conflict error if two packages require the same workspace `(repository, path)` at different commits.
Run this to update pinned revisions.

```bash
archml update-remote
```

---

### `archml sync-remote [-C <directory>]`

Download every workspace in the resolved closure to the local sync directory at the commits pinned in the lockfile.
Run `update-remote` first if the lockfile does not exist yet.

```bash
archml sync-remote
```

---

## License

Apache 2.0
