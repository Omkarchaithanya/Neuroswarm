# Budget Envelope Architecture (ARMORA)

> **Ownership:** Budget Envelope belongs **only** to ARMORA. Peers (HAOE, DIPA, RTG, MAKS, Router, AROP) receive injected ports — connectors, not ownership.

## Mission

Every request entering ARMORA owns exactly one **immutable** `BudgetEnvelope`. The envelope is the runtime resource contract: cost, latency, CPU, memory, energy, tokens, KV, tools, retries, streaming, concurrency, SLA, quality, and hardware preferences.

This is **not** a LiteLLM-style gateway spend tracker. It is a multi-dimensional OS contract inspired by Kubernetes LimitRange/ResourceQuota and Linux cgroups, specialized for ARM-native inference.

## Problem solved

NEXUS previously had three parallel budgets:

| Layer | What it tracked |
|-------|-----------------|
| `ArmoraBudgetPolicy` | USD + memory bytes + cache entries |
| RTG `BudgetEnvelope` | Thinking tokens + cost + energy + latency |
| OKF `BudgetManager` | Soft context token ceilings |

ARMORA Budget unifies them into one ledger with estimate → reserve → reconcile accounting.

## Placement

```
neuroswarm_arm/armora/budget/   # ownership
docs/budget/                    # this documentation
tests/armora/budget/            # pytest suite
```

Composition root: `neuroswarm_arm/main.py` builds the budget service and injects it into MAKS / Gateway / ARMORA client / RTG adapters.

## Core types

| Type | Role |
|------|------|
| `BudgetEnvelope` | Frozen per-request contract (limits, SLA, preferences) |
| `BudgetCategory` | Per-dimension limit/consumed/remaining/estimated/projected/violation |
| `BudgetRuntimeState` | Mutable tracker state keyed by `envelope_id` |
| `ExecutionAccounting` | Observed tokens, CPU, wall, memory, KV, tools, cost, energy |
| `BudgetLedger` | estimate → reserve → consume → reconcile |
| `PolicyEngine` | Agent/role → envelope template |
| `BudgetOptimizer` | Configurable degrade ladder until feasible |
| `BudgetLifecycle` | Create → Validate → Freeze → Execute → Report → Persist |

## Category dimensions

`LatencyBudget`, `CostBudget`, `TokenBudget` (prompt/completion/reasoning), `MemoryBudget`, `EnergyBudget`, `KVBudget`, `ToolBudget`, `ComputeBudget`, `StreamingBudget`, `RetryBudget`.

Each category exposes: `limit`, `consumed`, `remaining`, `estimated`, `projected`, `violation`, `confidence`, `hardness` (`soft`|`hard`).

## Immutability rule

After `freeze()`, the envelope object never mutates. Only `BudgetTracker` updates `BudgetRuntimeState`. Mid-flight degrade actions update runtime state and emit telemetry — they do not rewrite the frozen contract.

## Peer integration

```
POST /v1/chat
  → Gateway seeds envelope (PolicyEngine)
  → Lifecycle.validate + freeze
  → HAOE / Router / DIPA / RTG / MAKS / ACR consult remaining
  → Tracker reserve/reconcile on each consume
  → Reports + Persistence + Telemetry
  → AROP observes budget_* metrics (never mutates frozen envelopes)
```

| Peer | Obligation |
|------|------------|
| Gateway | Create + freeze; put `envelope_id` in baggage |
| ARMORA | Refuse generate without frozen envelope; charge via ledger |
| HAOE | Consult before tool/retry/cascade |
| DIPA | Afford checks for tier/quant/speculation/batch/timeout |
| Router | Rank tools using remaining cost (compat `budget_remaining_usd`) |
| RTG | `ReasoningBudgetView` over token/cost/energy/latency dims |
| MAKS | `IARMORAPolicy.admit` from memory/KV dims |
| AQR | Prefer envelope quantization if affordable |
| AWPP | Skip prefetch when residual memory/energy too low |
| ACR/OKF | Clip context to prompt token budget |
| AROP | Tune **templates** via knobs; never mutate live envelopes |

## Three-phase ledger

1. **Estimate** — p50/p90 projection from cost/energy/KV models  
2. **Reserve** — optimistic lock against remaining hard dims  
3. **Reconcile** — apply actual − reserved; export `budget_estimate_error`

## Feasibility before optimization

Hard dims must satisfy `projected ≤ remaining`. Soft dims become multi-objective targets (quality, latency, cost, memory, energy). Optimizer returns a degrade path; policy picks among Pareto-feasible plans.

## Telemetry

Prometheus/OTel series (bounded labels: tenant, agent, workflow, tier):

- `budget_remaining`, `budget_reserved`, `budget_admit_total`
- `budget_violation_total`, `budget_estimate_error`
- `budget_tokens_per_usd`, `budget_tokens_per_watt`
- `budget_optimizer_degrades_total`

## Related docs

- [lifecycle.md](lifecycle.md)
- [cost-model.md](cost-model.md)
- [energy-model.md](energy-model.md)
- [developer.md](developer.md)
- [extension.md](extension.md)
- [plugin-guide.md](plugin-guide.md)
