# Budget Envelope — Extension Guide

## Add a new budget dimension

1. Subclass or register a `BudgetCategory` via plugin (`register_dimension`).
2. Add default limit keys to `BudgetRuntimeConfig` (env-backed).
3. Teach `ICostModel` / `IEnergyModel` / custom estimator to project the dim.
4. Optionally add degrade actions that free that dim.
5. Export `budget_remaining{dim=<name>}` via telemetry plugin.

No edits to DIPA/HAOE/MAKS required if they consult the generic remaining map.

## Add a cost model

Implement `ICostModel` and register:

```python
from neuroswarm_arm.armora.budget.plugins import register_cost_model
from neuroswarm_arm.armora.budget.ports import ICostModel

@register_cost_model("spot_amortized")
class SpotAmortizedCostModel:
    def project(self, op, hardware, cache_state):
        ...
```

Select with `NSA_BUDGET_COST_MODEL=spot_amortized`.

## Add an energy model

Same pattern with `@register_energy_model` / `NSA_BUDGET_ENERGY_MODEL`.

## Add a persistence backend

Implement `IPersistence` (`write_envelope`, `write_report`, `query_history`) and register with `@register_persistence`. Select via `NSA_BUDGET_PERSISTENCE=postgres`.

## Add a policy template

1. Add OKF policy markdown under `okf/policies/` or agent frontmatter.  
2. Or register a `PolicyCompiler` plugin that maps `agent_role → EnvelopeTemplate`.  
3. `PolicyEngine` merges config defaults + policy + request overrides.

## Tenant ResourceQuota

Use `TenantLedger` (in-process + SQLite) for aggregate caps. Optional Redis swarm ledger can be plugged as an `IAccountingProvider` without changing ARMORA core.

## AROP knobs

Map AROP `budget_usd` / `reasoning_cap` / `context_budget` to **policy template** fields. AROP must never call `envelope` mutation APIs on frozen instances.
