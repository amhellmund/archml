# ArchML Deployment Architecture

ArchML's deployment layer annotates the functional architecture with deployment intent. It describes how functional entities are packaged, where they run, how their channels are transported, and which credentials and artifact stores are involved. Deployment declarations never alter the functional architecture — they are purely additive.

Deployment declarations may appear **inline** inside functional entity bodies or in **separate `.archml` files** using `deployment` blocks. Both forms are equivalent and may coexist; conflicting declarations for the same target are a validation error.

---

## Deployment Schema System

All deployment entities follow a unified two-form pattern that mirrors the functional layer's distinction between type definitions and entity declarations.

### Schema Definitions

A schema definition introduces a named kind with a set of typed fields. It uses a single name after the category keyword:

```
<category> <SchemaName> [extends <ParentSchema>] {
    [description]
    <field>: <type>
    ...
}
```

Schema definitions are reusable blueprints. They declare structure, not values.

```
protocol gRPC {
    package: String
    service: String
    method:  String
}

identity AzureServicePrincipal {
    tenant:    String
    client-id: String
    secret:    String
}

store ContainerRegistry {
    url:  String
    auth: requires identity
}

compute AzureBatch {
    account: String
    pool:    String
    auth:    requires identity
}

bundle ContainerImage {
    name:  String
    tag:   String
    store: requires store
}
```

### Instance Declarations

An instance declaration creates a named instance of a schema. It uses two names — the schema name followed by the instance name:

```
<category> <SchemaName> <InstanceName> {
    [description]
    <field>: <value>
    ...
}
```

```
identity AzureServicePrincipal PlatformPrincipal {
    tenant:    my-tenant-id
    client-id: Env:AZURE_CLIENT_ID
    secret:    ProdVault:platform-sp-secret
}

store ContainerRegistry PlatformACR {
    url:  platform.azurecr.io
    auth: PlatformPrincipal
}

compute AzureBatch OrderPool {
    account: Env:AZURE_BATCH_ACCOUNT
    pool:    order-processing-prod
    auth:    PlatformPrincipal
}

bundle ContainerImage OrderBundle {
    name:  order-service
    tag:   2.1.0
    store: PlatformACR
    packs component OrderService
    packs component NotificationSidecar
}
```

The grammar is unambiguous: one name before `{` (or `extends`) is a schema definition; two names before `{` is an instance declaration.

### Field Types in Schema Definitions

Schema fields use the same primitive and container types as the functional layer, plus a reference constraint type:

| Type                          | Description                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------- |
| `String`                      | Unicode string value                                                              |
| `Int`                         | Integer number                                                                    |
| `Bool`                        | Boolean value                                                                     |
| `Optional<T>`                 | Value that may be absent                                                          |
| `List<T>`                     | Ordered sequence of `T`                                                           |
| `requires identity`           | Field must be satisfied by any declared `identity` instance                       |
| `requires identity <Schema>`  | Field must be satisfied by an instance of the named `identity` schema             |
| `requires store`              | Field must be satisfied by any declared `store` instance                          |
| `requires store <Schema>`     | Field must be satisfied by an instance of the named `store` schema                |
| `requires compute`            | Field must be satisfied by any declared `compute` instance                        |
| `requires compute <Schema>`   | Field must be satisfied by an instance of the named `compute` schema              |
| `requires bundle`             | Field must be satisfied by any declared `bundle` instance                         |
| `requires bundle <Schema>`    | Field must be satisfied by an instance of the named `bundle` schema               |

A `requires <category>` field in a schema definition declares a dependency: the instance must provide the name of a declared instance of that category. The optional `<Schema>` name narrows the constraint to instances of a specific schema — the tooling validates both that the instance exists and that it was declared with the named schema. Schema inheritance is respected: an instance of a child schema satisfies a `requires` constraint for any of its ancestor schemas.

### Schema Inheritance

Any schema definition may extend a parent schema using `extends`. The child inherits all fields from the parent and may add new ones. Overriding an inherited field is a validation error. Inheritance cycles are a validation error.

```
compute CloudCompute {
    auth: requires identity
}

compute AzureBatch extends CloudCompute {
    account: String
    pool:    String
    # inherits: auth: requires identity
}

compute Kubernetes extends CloudCompute {
    cluster:   String
    namespace: String
    # inherits: auth: requires identity
}
```

Instances of a child schema must satisfy all fields from the full inheritance chain:

```
compute AzureBatch OrderPool {
    account: Env:AZURE_BATCH_ACCOUNT
    pool:    order-processing-prod
    auth:    PlatformPrincipal        # satisfies inherited field from CloudCompute
}
```

`extends` works across files. The parent schema must be imported before use (see [Multi-File Composition](#multi-file-composition)).

---

## Deployment Entities

### `protocol`

A `protocol` schema defines a transport binding — the set of fields that describe how a channel is carried over a specific mechanism. Protocol schemas have no instance form; they are always instantiated inline inside `bind` statements.

```
protocol SlackWebhook {
    url:           String
    channel:       String
    signing-token: String
}
```

The standard library provides commonly used protocols. They are protected and cannot be redefined, but user schemas may extend them:

```
protocol InternalHTTP extends HTTP {
    correlation-header: String
}
```

### `identity`

An `identity` schema describes an authentication credential. Instances hold the configuration needed to authenticate as a specific principal.

```
identity AzureServicePrincipal {
    tenant:    String
    client-id: String
    secret:    String
}

identity PersonalAccessToken {
    token: String
}
```

Instances:

```
identity AzureServicePrincipal PlatformPrincipal {
    tenant:    my-tenant-id
    client-id: Env:AZURE_CLIENT_ID
    secret:    ProdVault:platform-sp-secret
}

identity PersonalAccessToken DatabricksToken {
    token: ProdVault:databricks-pat
}
```

### `store`

A `store` schema describes a repository for artifacts of any kind — credentials, secrets, configuration values, container images, packages, or any other named item. A store instance declares its available artifacts using `artifact` statements.

```
store ContainerRegistry {
    url:  String
    auth: requires identity
}

store AzureKeyVault {
    vault-url: String
    auth:      requires identity
}
```

#### Artifact Declarations

A store instance declares its available artifacts using `artifact` statements. Each `artifact` names a value the store provides. Stores that serve as artifact repositories without individually named references (e.g., a container registry where the bundle schema holds the image name) may declare no artifacts.

```
store AzureKeyVault ProdVault {
    vault-url: Env:KEY_VAULT_URL
    auth:      BootstrapPrincipal

    artifact platform-sp-secret
    artifact databricks-pat
    artifact stripe-api-key
}

store ContainerRegistry PlatformACR {
    url:  platform.azurecr.io
    auth: PlatformPrincipal
    # no artifact declarations — bundle schema holds the image name
}
```

A store instance may also use `artifact *` to declare itself **open** — any `StoreName:name` reference is valid without an explicit declaration:

```
store EnvSecretStore {}
store EnvSecretStore Env {
    artifact *    # open: Env:ANYTHING is valid
}
```

A store instance that declares at least one `artifact` (or `artifact *`) may be referenced using the `StoreName:artifact` value syntax (see [Store Artifact References](#store-artifact-references)). Referencing a store with no artifact declarations in that syntax is a validation error.

The standard library provides `EnvSecretStore` — an open store that resolves values from the process environment. Its default instance `Env` accepts any artifact name without declaration.

### `compute`

A `compute` schema describes a platform on which bundles are executed.

```
compute DockerHost {}

compute Kubernetes {
    cluster:   String
    namespace: String
    auth:      requires identity
}

compute DatabricksCompute {
    workspace: String
    cluster:   String
    auth:      requires identity
}
```

Instances:

```
compute DockerHost LocalDocker {}

compute Kubernetes AKSCluster {
    cluster:   Env:AKS_CLUSTER_NAME
    namespace: ecommerce-prod
    auth:      PlatformPrincipal
}
```

### `bundle`

A `bundle` schema describes a deployable artifact. Instances pack one or more functional components or systems into a single artifact and reference the store from which the artifact is fetched.

```
bundle ContainerImage {
    name:  String
    tag:   String
    store: requires store
}

bundle PythonPackage {
    package: String
    version: String
    store:   requires store
}
```

#### `packs` Statements

Bundle instances use `packs` to declare which functional components or systems they contain. The same component or system may appear in multiple bundle instances — this is useful for per-environment bundles that pack the same component differently. The validation rule is per-resolved-variant: within any single variant and environment combination, a component or system must be packed by at most one deployed bundle.

```
# Packing individual components
bundle ContainerImage OrderBundle {
    name:  order-service
    tag:   2.1.0
    store: PlatformACR
    packs component OrderService
    packs component NotificationSidecar
}

# Packing a whole system — all components within it are included
bundle ContainerImage FulfillmentBundle {
    name:  fulfillment-service
    tag:   1.3.0
    store: PlatformACR
    packs system Fulfillment
}
```

When a bundle packs a system, all current and future components added to that system are automatically included. `packs component` and `packs system` may be mixed within one bundle instance.

---

## Store Artifact References

A field value of the form `StoreName:name` resolves the named artifact from the referenced store instance. The store must declare that artifact (either explicitly or via `artifact *`). The tooling validates both the store name and the artifact name statically.

```
identity AzureServicePrincipal PlatformPrincipal {
    tenant:    my-tenant-id                    # plain literal
    client-id: Env:AZURE_CLIENT_ID             # artifact from the standard Env store (open)
    secret:    ProdVault:platform-sp-secret    # artifact from a user-declared store
}
```

**Validation rules:**

- `StoreName` must be a declared store instance.
- `StoreName` must declare the referenced artifact explicitly, or declare `artifact *`.
- Referencing a store with no artifact declarations in this syntax is a validation error.

Plain literal values and store artifact references may be used interchangeably for `String` fields. The choice is the author's; the tooling does not restrict which fields may use store artifact references.

---

## Deployment Statements

Two statements attach deployment intent to functional entities: `bind` and `deploy`. Both may appear inline inside `system` or `component` bodies, or inside external `deployment` blocks.

### `bind`

`bind` attaches a protocol instantiation to a channel. The channel carries the interface — the tooling infers the interface from the functional architecture. The protocol fields are validated against the referenced protocol schema.

```
bind [$<channel>] via <Protocol> {
    <field>: <value>
    ...
}
```

A `bind` statement may only reference channels declared at the **same scope** in the functional architecture. A channel declared inside a sub-system or sub-component is not visible in the enclosing scope's `bind` statements. Binding the same channel more than once — in any combination of inline and external declarations — is a validation error.

```
system ECommerce {
    connect OrderService.PaymentRequest -> $payment -> PaymentService.PaymentRequest
    connect OrderService.OrderReady    -> $notify  -> NotificationService.OrderReady

    # $payment and $notify are declared at this scope — legal to bind here
    bind $payment via gRPC {
        package: payments.v1
        service: PaymentService
        method:  ProcessPayment
    }

    bind $notify via SlackWebhook {
        url:           Env:SLACK_WEBHOOK_URL
        channel:       Env:SLACK_CHANNEL
        signing-token: ProdVault:slack-signing-token
    }
}
```

### `bind config`

`bind config` resolves a named configuration dependency — declared with `config` in the functional layer — to a concrete store instance. The store provides the configuration values at runtime.

```
bind config <config_name> to store [<SchemaType>] <InstanceName>
```

`<config_name>` must match a `config` declaration on the functional entity being annotated. The optional `<SchemaType>` constrains the store to a specific schema (using the schema-typed reference described in [Field Types in Schema Definitions](#field-types-in-schema-definitions)). Omitting it accepts any store instance.

```
deployment component Consumer {
    bind config DbConfig to store AzureKeyVault ProdVault
    bind config FeatureFlags to store AzureStorage AppConfigStore
    deploy bundle ConsumerBundle on compute AKSCluster
}
```

Per-environment bindings let you swap the backing store without touching the functional or bundle declarations:

```
deployment[prod] component Consumer {
    bind config DbConfig to store AzureKeyVault ProdVault
}

deployment[dev] component Consumer {
    bind config DbConfig to store EnvSecretStore Env
}
```

`bind config` may also appear inline inside a functional entity body, after all functional statements:

```
component Consumer {
    requires DataMessage
    config DbConfig

    bind config DbConfig to store AzureKeyVault ProdVault
}
```

A `bind config` statement may only reference a `config` name declared on the same entity. Binding the same config name more than once within the same variant and environment combination is a validation error.

### `deploy`

`deploy` assigns a bundle instance to a compute instance for a functional component or system. When placed inside a functional entity body or a `deployment` block scoped to that entity, it declares how that entity is executed.

```
deploy bundle <BundleName> on compute <ComputeName>
```

When a bundle packs an entire system (via `packs system`), the `deploy` statement is placed inside the `deployment` block for that system. It deploys all components within the system together.

```
deployment system Fulfillment {
    deploy bundle FulfillmentBundle on compute AKSCluster
}
```

Deploying the same component or system more than once within the same variant and environment — in any combination of inline and external declarations — is a validation error.

---

## Inline Deployment

`bind` and `deploy` are optional statements in any `system` or `component` body. They appear after functional statements (`requires`, `provides`, `connect`, `expose`) and do not affect functional semantics.

```
component OrderService {
    """Accepts and validates customer orders."""

    requires PaymentRequest
    provides OrderConfirmation

    deploy bundle OrderBundle on compute AKSCluster
}

system ECommerce {
    use component OrderService
    use component PaymentService

    connect OrderService.PaymentRequest -> $payment -> PaymentService.PaymentRequest

    bind $payment via gRPC {
        package: payments.v1
        service: PaymentService
        method:  ProcessPayment
    }
}
```

Inline deployment is optional. Functional files with no deployment statements are valid; the deployment layer may be added separately.

---

## External Deployment Blocks

A `deployment` block in a separate file mirrors the functional nesting of a system or component and adds deployment declarations without touching the functional file. Deployment blocks may be nested to reach inner scopes.

```
deployment system <Name> [env_ann] [variant_ann] { <deployment_body> }
deployment component <Name> [env_ann] [variant_ann] { <deployment_body> }
```

A deployment body contains any combination of `bind` statements, `deploy` statements, and nested `deployment` blocks. Nesting must match the functional hierarchy — a `deployment system Fulfillment` nested inside `deployment system ECommerce` is only valid if `Fulfillment` is a sub-system of `ECommerce` in the functional architecture.

Functional entities referenced in a deployment block (as targets of `bind`, `deploy`, or nested `deployment` blocks) are resolved by name against the global functional namespace assembled from all `.archml` files in the build. No `use` declaration is needed inside a deployment block; the tooling knows what is structurally available.

```
# arch/deployment/prod.archml

from deployment/infra   import AKSCluster, PlatformPrincipal
from deployment/stores  import PlatformACR, ProdVault
from deployment/bundles import OrderBundle, FulfillmentBundle

deployment[prod] system ECommerce {

    bind $payment via gRPC {
        package: payments.v1
        service: PaymentService
        method:  ProcessPayment
    }

    deployment component OrderService {
        deploy bundle OrderBundle on compute AKSCluster
    }

    deployment system Fulfillment {

        bind $shipment via HTTP {
            method: POST
            path:   /api/v1/shipments
        }

        deploy bundle FulfillmentBundle on compute AKSCluster
    }
}
```

Inline deployment and external deployment blocks may coexist. The tooling merges them; any conflict (same channel bound twice, same entity deployed twice in the same variant and environment) is a validation error regardless of which file the conflicting declarations appear in.

---

## Top-Level Deployment Statements

`bind` and `deploy` may appear at the top level of an `.archml` file — outside any `system`, `component`, or `deployment` block. This is the deployment equivalent of top-level `connect` statements in the functional layer.

Top-level `bind` may only reference channels declared at the top level of any file in the build (i.e., channels introduced by top-level `connect` statements). Top-level `deploy` may only target components or systems declared at the top level.

```
# Top-level functional declarations (may be in a different file)
# connect UserFacing.OrderRequest -> $entry -> ECommerce.OrderRequest

# Top-level deployment statements
bind $entry via HTTP {
    method: POST
    path:   /api/v1/orders
}

deploy bundle GatewayBundle on compute AKSCluster
```

The same conflict rule applies: a top-level `bind` or `deploy` conflicts with an inline or block-level declaration targeting the same channel or entity.

---

## Scoping Rules

**`bind` scope:** A `bind` statement may only reference a channel (`$name`) that is declared in the same functional scope — either the `system` or `component` body where the `bind` appears, or the corresponding functional scope matched by an enclosing `deployment` block. Channels from inner or outer scopes are not accessible.

**`deploy` scope:** A `deploy` statement inside a `deployment system S` or `deployment component C` applies to `S` or `C` respectively. When the bundle packs a system via `packs system`, the `deploy` statement must appear inside the `deployment` block for that system.

**Conflict rule:** Binding the same channel more than once, or deploying the same component or system more than once within the same variant and environment combination, is a validation error. This applies across all files and across inline and external declarations.

**Functional name resolution:** A `deployment system X` or `deployment component X` block resolves `X` from the global functional namespace. If no `system X` or `component X` exists in the build, it is a validation error.

---

## Standard Library

The standard library ships a set of pre-defined protocol, store, and compute schemas. Standard library definitions are **protected** — they cannot be redefined. User schemas may extend them.

### Protocols

| Name             | Fields                                             |
| ---------------- | -------------------------------------------------- |
| `HTTP`           | `method: String`, `path: String`                   |
| `gRPC`           | `package: String`, `service: String`, `method: String` |
| `Kafka`          | `bootstrap: String`, `topic: String`               |
| `Amqp`           | `host: String`, `exchange: String`                 |
| `DatabaseTable`  | `connection: String`, `schema: String`, `table: String` |
| `DatabricksTable`| `workspace: String`, `catalog: String`, `schema: String`, `table: String` |

### Stores

| Schema           | Fields       | Notes                                     |
| ---------------- | ------------ | ----------------------------------------- |
| `EnvSecretStore` | *(none)*     | Open (`artifact *`); reads from process environment |

The standard library provides one `EnvSecretStore` instance named `Env`. It requires no `auth` and its `artifact *` declaration means any `Env:NAME` reference is valid without explicit declaration.

### Compute

| Schema    | Fields    | Notes                          |
| --------- | --------- | ------------------------------ |
| `Process` | *(none)*  | Local process; no container    |

---

## Variant and Environment Handling

The deployment layer supports two orthogonal annotation dimensions:

- **`<variant>`** — architectural or structural alternatives (e.g., `cloud`, `on_premise`). Inherited from the functional layer; see the functional architecture reference for full semantics.
- **`[env]`** — deployment environment (e.g., `dev`, `qa`, `prod`). Deployment-layer only; has no meaning in functional declarations.

Both annotations are optional and independent. They may be combined on the same declaration:

```
deployment<cloud>[prod] system ECommerce { ... }
```

When only one dimension varies, omit the other:

```
deployment[prod] system ECommerce { ... }
deployment[dev]  system ECommerce { ... }
```

### Environment Annotations

Any deployment declaration accepts an optional `[env, ...]` annotation immediately after the keyword (and after any variant annotation):

```
identity[prod] AzureServicePrincipal ProdPrincipal {
    tenant:    prod-tenant
    client-id: Env:PROD_CLIENT_ID
    secret:    ProdVault:sp-secret
}

identity[dev] AzureServicePrincipal DevPrincipal {
    tenant:    dev-tenant
    client-id: Env:DEV_CLIENT_ID
    secret:    Env:DEV_CLIENT_SECRET
}

deployment[prod] system ECommerce {
    bind $payment via gRPC {
        package: payments.v1
        service: PaymentService
        method:  ProcessPayment
    }
    deployment component OrderService {
        deploy bundle OrderBundle on compute AKSCluster
    }
}

deployment[dev] system ECommerce {
    bind $payment via HTTP {
        method: POST
        path:   /dev/payment
    }
    deployment component OrderService {
        deploy bundle OrderBundle on compute LocalDocker
    }
}
```

Environment annotations propagate through nested `deployment` blocks the same way variant annotations do: a `deployment[prod]` block propagates `prod` to all nested statements and blocks unless overridden.

Declarations with no environment annotation are **baseline** — active in every environment.

### Combining Variants and Environments

`<variant>` and `[env]` are evaluated independently. A declaration annotated `<cloud>[prod]` is active when the architectural variant is `cloud` and the environment is `prod`. Each dimension is selected separately at build time; there is no implicit cross-product.

```
deployment<cloud>[prod] component OrderService {
    deploy bundle OrderBundle on compute AKSCluster
}

deployment<on_premise>[prod] component OrderService {
    deploy bundle OrderBundle on compute OnPremK8s
}
```

---

## Multi-File Composition

### Imports in Deployment Files

Deployment schema definitions and instance declarations are top-level declarations and follow the same multi-file rules as the functional layer.

`from ... import` brings deployment-layer definitions — schemas, instances, compute declarations, bundle declarations — from another file into scope:

```
from deployment/infra   import CloudCompute, VersionedArtifact
from deployment/stores  import PlatformACR, ProdVault
from deployment/bundles import OrderBundle, FulfillmentBundle

compute AzureBatch extends CloudCompute {
    account: String
    pool:    String
}
```

### Functional Entities in Deployment Files

Deployment files do **not** need to import the functional files they annotate. Functional entities (`system`, `component`, `user`) are resolved by name from the global functional namespace assembled across all `.archml` files in the build. A `deployment system ECommerce` block resolves `ECommerce` automatically; importing its source file is neither required nor meaningful.

If a `deployment` block names a functional entity that does not exist in the build, it is a validation error.

```
# arch/deployment/prod.archml
# — no import of systems/ecommerce needed —

from deployment/infra   import AKSCluster, PlatformPrincipal
from deployment/stores  import PlatformACR, ProdVault
from deployment/bundles import OrderBundle, FulfillmentBundle

store AzureKeyVault ProdVault {
    vault-url: Env:KEY_VAULT_URL
    auth:      BootstrapPrincipal

    artifact platform-sp-secret
}

deployment[prod] system ECommerce {

    bind $payment via gRPC {
        package: payments.v1
        service: PaymentService
        method:  ProcessPayment
    }

    deployment system Fulfillment {
        bind $shipment via HTTP {
            method: POST
            path:   /api/v1/shipments
        }
    }
}
```

`extends` may reference a parent schema from any imported file. Standard library schemas require no import — they are pre-loaded into every file's scope.

---

## Keyword Reference

| Keyword          | Purpose                                                                                        |
| ---------------- | ---------------------------------------------------------------------------------------------- |
| `protocol`       | Defines a transport binding schema, or extends an existing one.                                |
| `identity`       | Defines an authentication credential schema or declares a named instance.                      |
| `store`          | Defines an artifact repository schema, or declares a named instance.                           |
| `compute`        | Defines a compute platform schema, or declares a named instance.                               |
| `bundle`         | Defines a deployable artifact schema, or declares a named instance.                            |
| `extends`        | Inherits all fields from a parent schema (`identity Foo extends Bar { ... }`).                 |
| `requires`       | Field type constraint: the value must be a declared instance of the named category.            |
| `artifact`       | Declares a named artifact provided by a store instance; `artifact *` makes the store open.     |
| `packs`          | Declares which functional component or system a bundle instance contains.                      |
| `bind`           | Binds a channel to a protocol instantiation (`bind $ch via Protocol { ... }`).                 |
| `bind config`    | Resolves a functional `config` dependency to a store instance (`bind config X to store S`).    |
| `deploy`         | Assigns a bundle to a compute instance for a functional entity (`deploy bundle X on compute Y`). |
| `deployment`     | External deployment block mirroring functional nesting (`deployment system Name { ... }`).     |
| `via`            | Names the protocol in a `bind` statement.                                                      |
| `on`             | Names the compute instance in a `deploy` statement.                                            |
| `<variant>`      | Variant annotation on a declaration (architectural/structural dimension).                      |
| `[env]`          | Environment annotation on a deployment declaration (`dev`, `qa`, `prod`, etc.).                |
| `StoreName:name` | Resolves the named artifact from the referenced store instance.                                |

---

## Formal Grammar

The grammar below extends the functional architecture grammar. Non-terminals defined in the functional grammar (`IDENT`, `variant_ann`, `description`, `attribute`, `field_type`, `block_member`) are reused without redefinition.

Comments and whitespace are stripped by the lexer and do not appear in the grammar.

```ebnf
(* ── Top-level deployment declarations ─────────────────────── *)

deploy_decl     ::= deploy_category [ variant_ann ] [ env_ann ] IDENT deploy_decl_rest

deploy_category ::= 'protocol' | 'identity' | 'store' | 'compute' | 'bundle'

deploy_decl_rest ::= [ 'extends' IDENT ] '{' schema_body '}'   (* schema definition *)
                   | IDENT '{' instance_body '}'                (* instance declaration *)

(* ── Schema definitions ─────────────────────────────────────── *)

schema_body ::= [ description ]
                { attribute }
                { schema_field }

schema_field ::= IDENT ':' schema_type

schema_type  ::= field_type                       (* reuses functional type system *)
               | 'requires' deploy_category [ IDENT ]   (* optional schema name for typed constraint *)

(* ── Instance declarations ──────────────────────────────────── *)

instance_body ::= [ description ]
                  { attribute }
                  { instance_member }

instance_member ::= instance_field
                  | artifact_stmt       (* valid in store instances only *)
                  | packs_stmt          (* valid in bundle instances only *)

instance_field ::= IDENT ':' field_value

field_value    ::= IDENT ':' IDENT    (* store artifact reference: StoreName:name *)
                 | IDENT              (* plain literal *)
                 | INTEGER

(* ── Store artifact declarations ────────────────────────────── *)

artifact_stmt ::= 'artifact' ( IDENT | '*' )

(* ── Bundle packs declarations ──────────────────────────────── *)

packs_stmt ::= 'packs' ( 'component' | 'system' ) IDENT

(* ── Deployment statements ──────────────────────────────────── *)

bind_stmt        ::= 'bind' [ variant_ann ] [ env_ann ] '$' IDENT 'via' IDENT '{' { instance_field } '}'

bind_config_stmt ::= 'bind' [ variant_ann ] [ env_ann ] 'config' IDENT 'to' 'store' [ IDENT ] IDENT

deploy_stmt      ::= 'deploy' [ variant_ann ] [ env_ann ] 'bundle' IDENT 'on' 'compute' IDENT

(* ── External deployment blocks ─────────────────────────────── *)

deployment_block ::= 'deployment' [ variant_ann ] [ env_ann ] ( 'system' | 'component' ) IDENT
                     '{' deployment_body '}'

deployment_body  ::= { deployment_member }

deployment_member ::= bind_stmt
                    | bind_config_stmt
                    | deploy_stmt
                    | deployment_block

(* ── Environment annotation ─────────────────────────────────── *)

env_ann ::= '[' IDENT { ',' IDENT } ']'

(* ── Extension to functional block_member ───────────────────── *)

(* The following productions extend block_member from the functional grammar:  *)
(*   block_member ::= ... | bind_stmt | bind_config_stmt | deploy_stmt         *)

(* ── Extension to functional file statement ─────────────────── *)

(* The following productions extend statement from the functional grammar:     *)
(*   statement ::= ... | deploy_decl | deployment_block | bind_stmt | bind_config_stmt | deploy_stmt *)
```
