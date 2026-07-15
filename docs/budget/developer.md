# Budget Envelope — Developer Guide

## Quick start

```python
from neuroswarm_arm.armora.budget import (
    build_budget_service,
    load_budget_config,
    PlanAction,
)

svc = build_budget_service()
envelope, state = await svc.create_and_freeze(
    request_id="req-1",
    tenant_id="tenant-a",
    agent_role="chat",
)
assert envelope.frozen

decision = svc.can_afford(envelope.envelope_id, PlanAction.tier(1))
if decision.affordable:
    svc.tracker.reserve(envelope.envelope_id, {"cost_usd": 0.001, "completion_tokens": 128})
    # ... run inference ...
    svc.tracker.reconcile(envelope.envelope_id, {"cost_usd": 0.0008, "completion_tokens": 96})

reports = await svc.finalize(envelope.envelope_id)
```

## Config

```python
from neuroswarm_arm.armora.budget import load_budget_config

cfg = load_budget_config()  # reads NSA_BUDGET_*
```

Key env vars: `NSA_BUDGET_DEFAULT_COST_USD`, `NSA_BUDGET_DEFAULT_REASONING_TOKENS`, `NSA_BUDGET_PERSISTENCE`, `NSA_BUDGET_WORK`, `NSA_BUDGET_PLUGINS`.

## Compat with ArmoraBudgetPolicy

```python
from neuroswarm_arm.armora import ArmoraBudgetPolicy, BudgetConfig

policy = ArmoraBudgetPolicy(BudgetConfig(max_cost_usd=0.05))
policy.admit(size_bytes=4096)
policy.charge(0.001)
```

`ArmoraBudgetPolicy` is a thin adapter over the unified ledger and still satisfies MAKS `IARMORAPolicy`.

## Package map

| Module | Responsibility |
|--------|----------------|
| `envelope.py` | Immutable envelope + freeze |
| `categories.py` | Dimension budgets |
| `tracker.py` | Runtime consume/reserve/reconcile |
| `estimator.py` | Resource projections |
| `accounting.py` | ExecutionAccounting |
| `optimizer.py` | Degrade ladder |
| `validator.py` | AdmitDecision |
| `lifecycle.py` | State machine |
| `persistence.py` | SQLite/DuckDB/Postgres/JSON/Parquet |
| `reports.py` | FinOps reports |
| `plugins.py` | Extension registry |
| `telemetry.py` | OTel/Prometheus |
| `policy.py` | Agent → template |
| `ports.py` | Protocols |
| `schemas.py` | Pydantic DTOs |
| `config.py` | Runtime config |

## Testing

```bash
pytest tests/armora/budget -q
```

## Rules

1. Never mutate a frozen envelope.  
2. Never hardcode production limits in peer code — read from envelope/config.  
3. Never import budget internals from DIPA/HAOE; use injected ports.  
4. Prefer `can_afford` before irreversible work.
