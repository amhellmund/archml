# ArchML Language Reference

ArchML is a text-based DSL for defining software architecture alongside code.
Functional architecture files use the `.farchml` extension.

---

## File Structure

A file contains one or more top-level declarations.
Declarations can be nested to express containment.

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

Descriptions may embed images with the standard Markdown syntax `![alt](src)`. Image
paths are resolved relative to the `.farchml` file that contains the description; a
leading `/` anchors the path at the workspace root, while `http(s)://` and `data:`
URLs are used as-is. When the architecture is exported to the standalone HTML viewer
(`archml export`), referenced local images are copied into an assets directory next to
the output file, so the viewer must be shared together with that assets directory.

**Custom Attributes** attach metadata to any entity using the `@name: values` syntax.
Values are comma-separated identifiers (no strings, no spaces within values).
Attributes are user-defined; the tooling does not interpret them — they can express tags, ownership, or any other domain-specific classification.

```
component OrderService {
    @team: platform
    @tags: critical, payments

    requires PaymentRequest
    provides OrderConfirmation
}
```

Multiple values on a single `@` line form a set.
An entity may have any number of `@` attributes.

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

The `enum` keyword defines a constrained set of named values.
Each value appears on its own line:

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

The `type` keyword defines a reusable data structure.
Fields use `name: Type` syntax, one per line:

```
type OrderItem {
    product_id: String
    quantity:   Int
    unit_price: Float
}
```

Custom types and enums can be used as field types.
Interfaces define port contracts and cannot appear as field types inside `type` or `interface` bodies.

---

## Core Entities

### Interface

An interface defines a contract — a named set of typed fields exchanged between architectural elements.
Interfaces are declared at the top level or inside components and systems.
Fields use `name: Type` syntax, one per line:

```
interface OrderRequest {
    """Payload for submitting a new customer order."""

    order_id:    String
    customer_id: String
    items:       List<OrderItem>
    currency:    String
}
```

`interface` defines contracts used on ports.
`type` defines building blocks composed into fields.
The distinction is semantic: interfaces appear on ports; types compose into fields.

### Component

A component is a module with a clear responsibility.
Components declare the interfaces they consume (`requires`) and produce (`provides`) as **ports**.

```
component OrderService {
    requires PaymentRequest
    requires InventoryCheck
    provides OrderConfirmation
}
```

Components can nest sub-components.
`connect` statements wire sub-components together.
Every port of every sub-component must either be wired by a `connect` or promoted to the enclosing boundary with `expose`:

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

    channel validation: ValidationResult

    connect Validator.ValidationResult -> $validation -> Processor.ValidationResult

    expose Validator.OrderRequest
    expose Processor.PaymentRequest
    expose Processor.OrderConfirmation
}
```

A port that is neither wired nor exposed is a validation error.
Components may not contain systems.

### System

A system groups components (or sub-systems) that work toward a shared goal.
Systems wire their members using `connect` and `expose`.
Systems may nest other systems for large-scale decomposition:

```
system Enterprise {

    system ECommerce {
        provides InventorySync
    }

    system Warehouse {
        requires InventorySync
    }

    channel inventory_sync: InventorySync

    connect ECommerce.InventorySync -> $inventory_sync -> Warehouse.InventorySync
}
```

### User

A user represents a human actor — a role or persona that interacts with the system.
Users are leaf nodes; they cannot contain sub-entities.

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

Every `requires` and `provides` declaration defines a **port** — a named connection point on the entity.
The port name defaults to the interface name; use `as` to assign an explicit name:

```
requires <Interface> [as <port_name>]
provides <Interface> [as <port_name>]
```

`requires` declarations appear before `provides`.
Port names must be unique within their entity.

### Channel Declarations

A **channel** is a named, typed conduit between ports.
Every channel name used in a `connect` statement must first be declared with a `channel` declaration in the same scope.

```
channel <name> : <Interface>

channel <name> : <Interface> {
    """Optional markdown description."""
    @attr: value
}
```

`<name>` is the channel identifier (used as `$name` in `connect` statements).
`<Interface>` is a required type annotation — the interface contract carried by the channel.
The optional body may contain a triple-quoted description and custom `@attr: val` attributes.
Variant annotation is supported: `channel<cloud> events: DomainEvent`.

Channel declarations can appear at file scope or inside a `component` or `system` body.
A body-scope channel is local to that scope and is not visible outside.
File-scope channels can be imported with the standard `from ... import` syntax.

```
# Local scope — only visible inside this system
system Order {
    channel payment: PaymentRequest
    channel confirmation: OrderConfirmation

    connect PaymentGateway.PaymentRequest -> $payment -> OrderService.PaymentRequest
    connect OrderService.OrderConfirmation -> $confirmation -> Customer.OrderConfirmation
}
```

```
# Shared channel declared at file scope and imported by multiple systems
channel DomainEvents: EventMessage {
    """All domain events flow through this channel."""
    @owner: platform-team
}
```

The tooling validates that both connected ports expose or require the channel's declared interface.
Using an undeclared `$name` in a `connect` statement is a semantic error.

### `connect`

`connect` statements wire ports via a declared channel.
They can appear inside `component` or `system` bodies, or at the top level of a `.farchml` file to wire top-level entities.

```
// Full chain: wires both endpoints via the channel
connect <src_port> -> $<channel> -> <dst_port>

// One-sided: wires one endpoint to the channel
connect <src_port> -> $<channel>
connect $<channel> -> <dst_port>
```

`<src_port>` and `<dst_port>` use the form `Entity.port_name` — an explicit port on a named child entity.

The arrow direction follows data flow: a `provides` port (producer) is always on the left; a `requires` port (consumer) is always on the right.

### Port Exposure: `expose`

`expose` promotes a sub-entity's port to the enclosing boundary.
A port that is neither wired by `connect` nor promoted by `expose` is a validation error.

```
expose Entity.port_name [as new_name]
```

The port name must always be specified (e.g., `Entity.port_name`); implicit port inference is not supported.
The optional `as` clause renames the port at the boundary.
`expose` composes across levels — a system can expose a port that was already exposed by an inner component.

### Configuration Dependencies: `config`

A `config` declaration names an external configuration dependency on a component or system.
It expresses that the entity requires externally-provided configuration of a known type, without committing to how or where that configuration is supplied.
The deployment layer resolves it to a concrete store.

```
config <TypeName> [as <config_name>]
```

`<TypeName>` refers to a `type` declaration and defines the expected shape of the configuration.
The configuration dependency name defaults to `<TypeName>`; use `as` to assign an explicit name.
Configuration dependency names must be unique within their entity.

```
type DbConfig {
    url:         String
    max_retries: Int
}

type FeatureFlags {
    enable_cache: Bool
    cache_ttl:    Int
}

component Consumer {
    requires DataMessage
    config DbConfig
    config FeatureFlags
}

component Worker {
    config DbConfig as worker_db    # explicit name
    config FeatureFlags
}
```

`config` declarations are distinct from ports: they cannot appear in `connect` or `expose` statements and do not participate in the functional data flow graph.
They are purely binding targets for the deployment layer.

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

`AuditLogger` is present when both `cloud` and `hybrid` are active.
`OrderService` is present in any `cloud` configuration.
Baseline entities have no annotation and are present in all configurations.

### Validation per Variant

All consistency checks (port coverage, dangling references, unused interfaces) are evaluated independently for each declared variant. A port wired in only one variant must be wired or exposed in every variant in which its owning entity appears.

---

## External Systems

The `external` modifier marks systems, components, or users that are outside the development boundary.
External entities appear in diagrams with distinct styling and cannot be decomposed (they are opaque):

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

## Templates

The `template` modifier marks a `system`, `component`, or `user` as a reusable **blueprint**.
A template is a complete definition, but it is never rendered on its own and may not be
referenced directly — it exists only to be instantiated with `use`.

```
template system PaymentPipeline {
    component Gateway   { provides PaymentRequest }
    component Processor { requires PaymentRequest  provides PaymentResult }
    channel pay: PaymentRequest
    connect Gateway.PaymentRequest -> $pay -> Processor.PaymentRequest
    expose Gateway.PaymentRequest
    expose Processor.PaymentResult
}

template component RetryBuffer { requires Msg  provides Msg }
template user     ServiceAccount { provides AdminCommand }
```

A template is declared at the top level (it cannot be nested inside another entity body)
and may be imported like any other definition. It is brought to life with `use`:

```
from shared/templates import PaymentPipeline

system Orders {
    use system PaymentPipeline      # an instance with PaymentPipeline's full internals
}
system Billing {
    use system PaymentPipeline      # an independent second instance
}
```

Rules:

- A template is **excluded** from the standalone landscape view; it appears only inside the
  hosts that instantiate it. Each instantiation is an independent copy, re-qualified under
  its host path, so a body-scoped channel like `pay` becomes `Orders::PaymentPipeline::pay`
  in one host and `Billing::PaymentPipeline::pay` in another — never a collision.
- Referencing a template directly in a top-level `connect` is an error; instantiate it with
  `use` instead.
- `external` and `template` cannot be combined (a blueprint is not an external entity).
- Instantiating a template **inside another template** is discouraged and produces a
  warning; the nested use is not expanded.
- A template that is never instantiated anywhere produces a warning.

`template` applies to `system`, `component`, and `user`. (A `user` is a leaf with no
internal structure, so a template user simply contributes its ports on instantiation.)

---

## Multi-File Composition

Large architectures are split across files.
Top-level declarations (`component`, `system`, `user`, `interface`, `type`, `enum`, `channel`) can appear in any `.farchml` file — they do not need to be nested inside a system.

### Imports

`from ... import` brings named definitions from another file into scope:

```
from dir/subdir/file import Entity
from dir/subdir/file import Entity1, Entity2
```

An optional `as` clause assigns a local alias, avoiding name conflicts across files:

```
from dir/subdir/file import Entity as LocalName
from dir/subdir/file import Entity1 as E1, Entity2
```

After aliasing, only the local alias is in scope — the original name is not visible.

The path omits the `.farchml` extension. The first path segment is a mnemonic name declared in the workspace configuration (see [Workspace Configuration](#workspace-configuration)).

### `use`

The `use` keyword **instantiates** an in-scope entity (local or imported) inside a system
or component body without redefining it.
Always includes the entity type:

```
use component OrderService
use system ECommerce
use user Customer
```

Instantiation is a real operation, not a shorthand reference: the instance carries a copy
of the definition's **boundary ports** (its own `requires`/`provides` plus any `expose`d
child ports) and, for containers, its full internal structure. The internal structure is
re-qualified under the host path (e.g. `Orders::OrderService::Validator`), so two systems
that each `use` the same definition get two independent instances.

The instance's boundary ports become available as `Entity.port_name` targets in `connect`
and `expose` statements within the enclosing scope, and — like any other sub-entity port —
each open port **must be wired by a `connect` or promoted with `expose`**, otherwise it is
a validation error. The definition's internal channels stay local to the instance and are
never reachable from the host.

### Cross-Repository Imports

To import from another workspace, prefix the path with `@alias`:

```
from @payments/services/payment import PaymentService
from @inventory/services/stock  import StockManager
```

`@alias` is a **locally chosen name** declared in the workspace configuration that
refers to an imported remote workspace.
When the `@` prefix is omitted, the current repository is assumed.

The alias is local to the importing workspace; the imported workspace's own `name:`
is its **canonical identity**. Two workspaces that import the same remote (even under
different aliases) therefore refer to the same architecture, and its entities are
unified into a single model node.

---

## Workspace Configuration

Every repository is also a workspace. A single `.archml-workspace.yaml` file at the repository root serves as both the per-repository configuration and the multi-repository workspace configuration.

Each entry in `source-imports` declares a **mnemonic** — a short name that maps to a directory path within the repository.
Import paths are resolved by matching their first segment against the declared mnemonic names.

```yaml
# .archml-workspace.yaml
name: myapp
build-directory: .farchml-build
source-imports:
  - name: interfaces
    local-path: src/architecture/interfaces
  - name: services
    local-path: src/architecture/services
  - name: types
    local-path: src/architecture/types
```

With this configuration, `from interfaces/order import OrderRequest` resolves to
`src/architecture/interfaces/order.farchml`.
A path whose first segment matches no declared mnemonic is a resolution error.

`archml init` creates a minimal workspace file with a single `source-imports` entry pointing to the repository root:

```yaml
name: myapp
build-directory: .farchml-build
source-imports:
  - name: myapp
    local-path: .
```

Cross-repository imports reference a remote workspace by the `@alias` prefix.
Remote workspaces are declared in `source-imports` with a `git-repository` URL, a
`revision`, and an optional repo-relative `path`:

```yaml
source-imports:
  - name: interfaces
    local-path: src/architecture/interfaces
  - name: payments
    git-repository: https://github.com/example/payments-service
    revision: main
  - name: inventory
    git-repository: https://github.com/example/platform-monorepo
    revision: v2.3.0
    path: services/inventory
```

- `name` is the **local alias** used as the `@alias` prefix in import paths. It must be
  unique within the workspace but is otherwise chosen freely by the importer.
- `revision` pins the import to a branch, tag, or commit; it is resolved to a commit SHA
  and stored in the lockfile.
- `path` is the repository-relative path to the imported workspace directory (the
  directory containing its own `.archml-workspace.yaml`). It defaults to the repository
  root, so a single repository may host **multiple workspaces** at different paths, each
  imported under its own alias.

Each imported workspace's identity is its own `name:`. The resolved reference
`(repository, commit, path)` is the unit used for conflict detection.

#### Transitive resolution and conflicts

Remote workspaces may themselves declare git imports. `archml update-remote` walks the
**full transitive graph**, resolving and recording every reachable workspace in the
lockfile (`.farchml-lockfile.yaml`). `archml sync-remote` then materialises that closure
under the sync directory (one checkout per identity).

Because each `(repository, path)` reference resolves to a single commit, the resolver
rejects the **diamond problem**: if two packages in the graph require the same workspace
at different commits, `update-remote` fails with a conflict error naming the conflicting
requirers. (Two references to the same repository and commit via different sub-paths are
allowed — they select different workspaces.)

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
| `config`      | Declares an external configuration dependency on a component or system (`config DbConfig`). |
| `as`          | Assigns an explicit name to a port or config dependency (`requires PaymentRequest as pay_in`). |
| `channel`     | Declares a named, typed channel (`channel events: EventMessage`). Required before any `$name` in `connect`. |
| `connect`     | Wires ports via a declared channel (`connect A.p -> $ch -> B.p`).                        |
| `expose`      | Promotes a sub-entity's port to the enclosing boundary (`expose Entity.port [as name]`). |
| `$channel`    | Channel reference in `connect`; the `$` prefix distinguishes channels from ports.        |
| `from`        | Source path in an import statement (`from path import Name`).                            |
| `import`      | Entities to bring into scope; always paired with `from`.                                 |
| `use`         | Instantiates an in-scope entity inside a system or component (`use component X`).        |
| `template`    | Marks a system, component, or user as a reusable blueprint, instantiated only via `use`. |
| `external`    | Marks a system, component, or user as outside the development boundary.                  |
| `<v1, v2>`   | Variant annotation on an entity or statement.                                            |
| `@attr: ...`  | Custom attribute on an entity; values are comma-separated identifiers.                   |
| `"""..."""`   | Markdown description at the top of any entity body.                                      |

---

## Formal Grammar

The grammar is written in EBNF.
Terminal strings appear in `'single quotes'`.
Brackets `[ ]` denote optional elements, braces `{ }` denote zero-or-more repetition, and parentheses `( )` denote grouping.
The `|` operator denotes alternation.

Comments (lines starting with `#`) and whitespace are stripped by the lexer and do not appear in the grammar.

```ebnf
(* ── Top level ─────────────────────────────────────── *)

file        ::= { statement }

statement   ::= import_stmt
              | use_stmt
              | connect_stmt
              | expose_stmt
              | entity_decl

(* ── Imports and use ───────────────────────────────── *)

import_stmt  ::= 'from' import_path 'import' import_item { ',' import_item }
import_path  ::= [ '@' IDENT '/' ] IDENT { '/' IDENT }
import_item  ::= IDENT [ 'as' IDENT ]

use_stmt    ::= 'use' entity_kind IDENT
entity_kind ::= 'component' | 'system' | 'user'

(* ── Entity declarations ────────────────────────────── *)

entity_decl ::= top_block_decl
              | channel_decl
              | interface_decl
              | type_decl
              | enum_decl

(* Top-level entities accept the 'template' or 'external' modifier;
   nested block declarations accept only 'external'. *)
top_block_decl ::= [ 'external' | 'template' ] entity_kind [ variant_ann ] IDENT '{' block_body '}'
block_decl     ::= [ 'external' ] entity_kind [ variant_ann ] IDENT '{' block_body '}'

block_body  ::= [ description ]
                { attribute }
                { block_member }

block_member ::= port_decl
               | config_decl
               | channel_decl
               | connect_stmt
               | expose_stmt
               | block_decl
               | use_stmt

(* ── Ports ──────────────────────────────────────────── *)

port_decl   ::= ( 'requires' | 'provides' ) [ variant_ann ] IDENT [ 'as' IDENT ]

(* ── Configuration dependencies ─────────────────────── *)

config_decl ::= 'config' [ variant_ann ] IDENT [ 'as' IDENT ]

(* ── Channel declarations ───────────────────────────── *)

channel_decl  ::= 'channel' [ variant_ann ] IDENT ':' IDENT [ '{' channel_body '}' ]
channel_body  ::= [ description ] { attribute }

(* ── Connect and expose ─────────────────────────────── *)

connect_stmt ::= 'connect' [ variant_ann ] connect_expr

connect_expr ::= port_ref '->' '$' IDENT '->' port_ref   (* full chain *)
               | port_ref '->' '$' IDENT                  (* source only *)
               | '$' IDENT '->' port_ref                  (* sink only *)

port_ref    ::= IDENT '.' IDENT

expose_stmt ::= 'expose' [ variant_ann ] port_ref [ 'as' IDENT ]

(* ── Interfaces, types and enums ────────────────────── *)

interface_decl ::= 'interface' [ variant_ann ] IDENT '{' [ description ] { field_decl } '}'
type_decl      ::= 'type'      [ variant_ann ] IDENT '{' [ description ] { field_decl } '}'
enum_decl      ::= 'enum'      [ variant_ann ] IDENT '{' [ description ] { IDENT }      '}'

field_decl  ::= IDENT ':' type_expr

type_expr   ::= primitive_type
              | 'List'     '<' type_expr '>'
              | 'Map'      '<' type_expr ',' type_expr '>'
              | 'Optional' '<' type_expr '>'
              | IDENT

primitive_type ::= 'String' | 'Int' | 'Float' | 'Bool'
                 | 'Bytes'  | 'Timestamp' | 'Datetime'
(* ── Variants ───────────────────────────────────────── *)

variant_ann ::= '<' IDENT { ',' IDENT } '>'

(* ── Annotations and descriptions ──────────────────── *)

attribute   ::= '@' IDENT ':' IDENT { ',' IDENT }

description ::= '"""' MARKDOWN_TEXT '"""'

(* ── Lexical rules ──────────────────────────────────── *)

IDENT         ::= ( LETTER | '_' ) { LETTER | DIGIT | '_' | '-' }
LETTER        ::= 'a'-'z' | 'A'-'Z'
DIGIT         ::= '0'-'9'
MARKDOWN_TEXT ::= (* any sequence of characters not containing '"""' *)
```