# ArchML

ArchML is a text-based DSL for defining software architecture alongside your code. Architecture files live in the repository, are version-controlled like any other source file, and stay in sync with the system they describe.

The core idea: define your architecture once as a model, then derive multiple views from it — interactive web diagrams, consistency reports, and embedded Sphinx documentation — without maintaining separate diagrams per tool.

## Why ArchML?

Architecture documentation drifts. Visual tools like Enterprise Architect or ArchiMate live outside the codebase, so diagrams rot while the code moves on. Lightweight alternatives like Mermaid embed diagrams in Markdown, but each diagram is standalone — there is no shared model, no cross-diagram consistency, and no drill-down navigation.

ArchML sits between these extremes:

- **Text-first** — `.archml` files are plain text, stored in git, reviewed in pull requests.
- **Model-based** — one model, many views. Define a component once; reference it everywhere.
- **Consistency checking** — the tooling catches dangling references, unused interfaces, and disconnected components.
- **Navigable views** — drill down from system landscape to individual component internals.
- **Sphinx-native** — embed live architecture views directly in your documentation.

## Quick Example

A small e-commerce backend expressed in ArchML:

```
// types.archml

type OrderItem {
    field product_id: String
    field quantity:   Int
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
    field order_id:   String
    field customer_id: String
    field items:      List<OrderItem>
}

interface OrderConfirmation {
    field order_id:     String
    field status:       OrderStatus
    field confirmed_at: Timestamp
}

interface PaymentRequest {
    field order_id: String
    field amount:   Decimal
    field currency: String
}

interface InventoryCheck {
    field product_id: String
    field quantity:   Int
}
```

```
// systems/ecommerce.archml
from types import OrderRequest, OrderConfirmation, PaymentRequest, InventoryCheck

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
    description = "Customer-facing online store."

    // Channels decouple providers from requirers — no explicit wiring between pairs
    channel order_in:   OrderRequest
    channel order_out:  OrderConfirmation
    channel payment:    PaymentRequest {
        protocol = "gRPC"
        async = true
    }
    channel inventory:  InventoryCheck {
        protocol = "HTTP"
    }

    user Customer {
        provides OrderRequest   via order_in
        requires OrderConfirmation via order_out
    }

    component OrderService {
        title = "Order Service"
        description = "Accepts, validates, and processes customer orders."

        // Internal channel wires Validator to Processor without naming either
        channel validation: ValidationResult

        component Validator {
            requires OrderRequest
            provides ValidationResult via validation
        }

        component Processor {
            requires ValidationResult via validation
            requires PaymentRequest
            requires InventoryCheck
            provides OrderConfirmation
        }

        // Unbound ports (OrderRequest, PaymentRequest, etc.) are visible at the boundary
    }

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

Large architectures split naturally across files. A `from ... import` statement brings named definitions into scope; `use component X` places an imported component inside a system without redefining it. Remote repositories can be referenced with `@repo-name` prefixes for multi-repo workspace setups.

## Language at a Glance

| Keyword                   | Purpose                                                                           |
| ------------------------- | --------------------------------------------------------------------------------- |
| `system`                  | Group of components or sub-systems with a shared goal                             |
| `component`               | Module with a clear responsibility; may nest sub-components                       |
| `user`                    | Human actor (role or persona) that interacts with the system                      |
| `interface`               | Named contract of typed data fields; supports `@v1`, `@v2` versioning             |
| `channel name: Interface` | Named conduit within a system or component scope; decouples providers from requirers |
| `type`                    | Reusable data structure (used within interfaces)                                  |
| `enum`                    | Constrained set of named values                                                   |
| `field`                   | Named, typed data element with optional `description` and `schema`                |
| `requires` / `provides`   | Declare consumed and exposed interfaces on a component, system, or user           |
| `requires X via channel`  | Bind a `requires` declaration to a named channel                                  |
| `provides X via channel`  | Bind a `provides` declaration to a named channel                                  |
| `external`                | Marks a system, component, or user as outside the development boundary            |
| `from … import`           | Bring specific definitions from another file into scope                           |
| `use component X`         | Place an imported entity inside a system                                          |
| `tags`                    | Arbitrary labels for filtering and view generation                                |

Primitive types: `String`, `Int`, `Float`, `Decimal`, `Bool`, `Bytes`, `Timestamp`, `Datetime`
Container types: `List<T>`, `Map<K, V>`, `Optional<T>`
Filesystem types: `File` (with `filetype`, `schema`), `Directory` (with `schema`)

Multi-line descriptions use triple-quoted strings:

```
description = """
Accepts and validates customer orders.
Delegates payment to PaymentGateway.
"""
```

Enum values and channel block attributes each occupy their own line — no commas needed.

Full syntax reference: [docs/LANGUAGE_SYNTAX.md](docs/LANGUAGE_SYNTAX.md)

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

Initialize a new ArchML workspace. Creates `.archml-workspace.yaml` in the given directory with `<name>` as the workspace identity.

```bash
archml init my-service .
```

---

### `archml check [directory]`

Parse and validate all `.archml` files in the workspace. Reports dangling references, unused interfaces, and other consistency errors. Exits with a non-zero status if any errors are found.

```bash
archml check
archml check /path/to/workspace
```

---

### `archml visualize <entity> <output> [directory]`

Render a box diagram for a system or component and write it to a file. The entity path uses `::` as a separator for nested elements.

```bash
archml visualize ECommerce diagram.svg
archml visualize ECommerce::OrderService order_service.png
```

> [!NOTE]  
> This command exists, but is not yet working properly.


---

### `archml serve [directory]`

Launch an interactive web-based architecture viewer. Opens a browser UI for exploring the full architecture with drill-down navigation.

```bash
archml serve
archml serve --port 9000
archml serve --host 0.0.0.0 --port 8080
```

> [!NOTE]  
> This command exists, but is not yet working properly.

---

### `archml update-remote [directory]`

Resolve branch or tag references in the workspace configuration to their latest commit SHAs and write them to the lockfile (`.archml-lock.yaml`). Run this to update pinned revisions.

```bash
archml update-remote
```

---

### `archml sync-remote [directory]`

Download remote git repositories to the local sync directory at the commits pinned in the lockfile. Run `update-remote` first if the lockfile does not exist yet.

```bash
archml sync-remote
```

---

## Project Status

ArchML is in early development. The functional architecture domain (systems, components, interfaces, channels) is implemented. Behavioral and deployment domains are planned.

See [docs/PROJECT_SCOPE.md](docs/PROJECT_SCOPE.md) for the full vision and roadmap.

## License

Apache 2.0
