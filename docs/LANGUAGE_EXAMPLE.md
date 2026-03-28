# ArchML Language — Annotated Example

This walkthrough shows a small but realistic e-commerce architecture modelled in ArchML. It covers every major language feature: types, interfaces, artifacts, components with internal structure, systems, users, external actors, cross-file imports, and variants.

---

## Repository Layout

```
archml.yaml              # virtual filesystem roots
types.archml             # shared data types and interfaces
components/
  order_service.archml   # composite component with internal wiring
systems/
  ecommerce.archml       # top-level system composing all components
```

```yaml
# archml.yaml
roots:
  types:      types.archml
  components: components
  systems:    systems
```

---

## Shared Types and Interfaces — `types.archml`

```
# Primitive building block used inside interfaces.
# type defines a structure; it is not a port contract itself.
type OrderItem {
    product_id: String
    quantity:   Int
    unit_price: Float
}

# Enum values are bare identifiers, one per line.
enum OrderStatus {
    Pending
    Confirmed
    Shipped
    Delivered
    Cancelled
}

# Interfaces define port contracts. Fields use name: Type syntax.
interface OrderRequest {
    order_id:    String
    customer_id: String
    items:       List<OrderItem>
}

interface OrderConfirmation {
    order_id:     String
    status:       OrderStatus
    confirmed_at: Timestamp
}

interface PaymentRequest {
    order_id: String
    amount:   Float
    currency: String
}

interface PaymentResult {
    order_id:       String
    success:        Bool
    transaction_id: Optional<String>
}

interface InventoryCheck {
    product_id: String
    quantity:   Int
}

interface ValidationResult {
    order_id: String
    valid:    Bool
}

# Artifacts model opaque data shapes (files, blobs, streams).
# Their concrete form is specified in deployment architecture.
artifact MonthlyReport {
    """PDF summary of monthly sales figures per region."""
}

interface ReportOutput {
    report: MonthlyReport
}
```

---

## Composite Component — `components/order_service.archml`

```
from types import OrderRequest, ValidationResult, PaymentRequest, InventoryCheck, OrderConfirmation

# Custom attributes express ownership and classification metadata.
# Values are identifiers; tooling does not interpret them.
component OrderService {
    """Accepts, validates, and processes customer orders."""

    @team: platform
    @tags: critical, orders

    # Sub-components are private implementation detail.
    # Their ports must all be accounted for within this body.
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

    # connect wires an internal channel between two sub-components.
    # $validation is the channel name; it is local to this scope.
    connect Validator.ValidationResult -> $validation -> Processor.ValidationResult

    # expose promotes sub-component ports to the OrderService boundary.
    # Any port that is neither wired nor exposed is a validation error.
    expose Validator.OrderRequest
    expose Processor.PaymentRequest
    expose Processor.InventoryCheck
    expose Processor.OrderConfirmation
}
```

After `expose`, `OrderService` presents four ports at its boundary:
`OrderRequest`, `PaymentRequest`, `InventoryCheck`, and `OrderConfirmation`.
The internal `$validation` channel and both sub-components are invisible to callers.

---

## Top-Level System — `systems/ecommerce.archml`

```
from types import OrderRequest, OrderConfirmation, PaymentRequest, PaymentResult, InventoryCheck
from components/order_service import OrderService

system ECommerce {
    """Customer-facing online store."""

    @domain: commerce
    @tags: customer-facing, commerce

    # user is a leaf node representing a human actor.
    # It declares the same requires/provides ports as components.
    user Customer {
        """An end user who places orders."""

        provides OrderRequest
        requires OrderConfirmation
    }

    # use places an already-imported component into this scope.
    # Its boundary ports become available for connect and expose.
    use component OrderService

    component PaymentGateway {
        provides PaymentRequest
        requires PaymentResult
    }

    component InventoryManager {
        provides InventoryCheck
    }

    # external marks a system outside the development boundary.
    # It is opaque — it cannot be decomposed further.
    external system StripeAPI {
        requires PaymentRequest
        provides PaymentResult
    }

    # Wire the Customer to OrderService.
    connect Customer.OrderRequest       -> $order_in    -> OrderService.OrderRequest
    connect OrderService.OrderConfirmation -> $order_out -> Customer.OrderConfirmation

    # Wire backing services to OrderService.
    connect PaymentGateway.PaymentRequest  -> $payment   -> OrderService.PaymentRequest
    connect InventoryManager.InventoryCheck -> $inventory -> OrderService.InventoryCheck

    # Wire PaymentGateway to the external Stripe API.
    connect PaymentGateway.PaymentRequest -> $stripe        -> StripeAPI.PaymentRequest
    connect StripeAPI.PaymentResult       -> $stripe_result -> PaymentGateway.PaymentResult
}
```

All ports in the system are internally wired. No `expose` is needed here — `ECommerce` has no external callers modelled in this file.

---

## Adding Variants

Variants model multiple architectural configurations within the same file. The `<v1, v2>` annotation marks which variants an entity or statement belongs to. Unannotated entities are **baseline** — present in every variant.

```
from types import PaymentRequest, PaymentResult

system<cloud> ECommerce {

    # OrderService is baseline within the cloud variant (inherited from system).
    use component OrderService

    # PaymentGateway exists only in the cloud variant.
    component<cloud> PaymentGateway {
        provides PaymentRequest
        requires PaymentResult
    }

    # LocalPaymentProcessor exists only in the on_premise variant.
    # Because it is inside a cloud-annotated system, its effective set
    # is {cloud, on_premise} — it appears when both are active.
    component<on_premise> LocalPaymentProcessor {
        provides PaymentRequest
    }

    # These connect statements are themselves variant-scoped.
    connect<cloud>       PaymentGateway.PaymentRequest       -> $payment -> OrderService.PaymentRequest
    connect<on_premise>  LocalPaymentProcessor.PaymentRequest -> $payment -> OrderService.PaymentRequest
}
```

The tooling validates port coverage independently for each variant. In the `cloud` variant, `OrderService.PaymentRequest` is wired by the first `connect`. In the `on_premise` variant, it is wired by the second. Both variants are individually valid.

Multiple variants can be listed in a single annotation when a declaration belongs to more than one:

```
component<cloud, hybrid> AuditLogger {
    requires OrderConfirmation
}
```

`AuditLogger` is present when `cloud` is active, when `hybrid` is active, or when both are active simultaneously.
