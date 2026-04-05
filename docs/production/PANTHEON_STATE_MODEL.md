# Pantheon State Model

The Pantheon is a structured multi-agent negotiation system utilizing finite state machines. Ad-hoc string manipulation or local variable states for objections are strictly prohibited in the final product.

## 1. Objection Lifecycle (`ObjectionLifecycleMachine`)

An objection (e.g., raised by Athena or Apollo) traverses explicit boundaries.
* `OPEN`: Raised legitimately and requiring resolution.
* `RESOLVED`: Adjudicated via translation reforge or explicitly dismissed.
* `ESCALATED`: A resolution was attempted but failed, escalating to the Council Phase.

Transitions outside the allowed state vectors raise a `PantheonStateError`.

## 2. Council Phase Machine (`CouncilPhaseMachine`)

Phase sequences strictly track the deliberative process:
* `PREPARE` → `SCREEN` → `INDEPENDENT_BALLOT` → `COUNCIL` (optional loop) → `FINALIZE`.

## 3. The Resolution Binding Rule

A "Reforge" cycle generated via the translation loop MUST successfully map `addressed_objection_id` outputs against currently active `OPEN` objections in the ledger.
If a translator output references hallucinated objection IDs or fails to map its modifications back to the ledger state canonically, the discharge fails, and the objection remains `OPEN`. Silent guesswork is forbidden.

## 4. Persisted Arbitrage (`CouncilArtifactStore`)
Every state transition boundary creates an auditable record serialized to the `CouncilArtifactStore`.
This guarantees that a human operator can read an explainable causal chain outlining exactly why a given component was blocked by Athena and how Hermes repaired it.
