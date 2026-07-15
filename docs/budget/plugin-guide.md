# Budget Envelope — Plugin Guide

## Registry

`neuroswarm_arm.armora.budget.plugins.BudgetPluginRegistry` holds:

| Hook | Decorator | Env |
|------|-----------|-----|
| Cost model | `@register_cost_model(name)` | `NSA_BUDGET_COST_MODEL` |
| Energy model | `@register_energy_model(name)` | `NSA_BUDGET_ENERGY_MODEL` |
| Estimator | `@register_estimator(name)` | `NSA_BUDGET_ESTIMATOR` |
| Persistence | `@register_persistence(name)` | `NSA_BUDGET_PERSISTENCE` |
| Policy compiler | `@register_policy_compiler(name)` | `NSA_BUDGET_POLICY_COMPILER` |
| Dimension | `@register_dimension(name)` | — |
| Telemetry exporter | `@register_telemetry(name)` | `NSA_BUDGET_TELEMETRY` |
| Accounting provider | `@register_accounting(name)` | — |

## Discovery

1. Built-in registrations at import time.  
2. Extra modules listed in `NSA_BUDGET_PLUGINS` (comma-separated import paths).  
3. Optional Python entry points group `nexus_arm.budget_plugins`.

## Stub rule

Plugins must be real callable implementations. Missing optional deps (DuckDB, Postgres driver, pyarrow) degrade to a clear `BackendUnavailableError` with install hint — never silent no-ops for persistence writes when that backend is selected.

## Example: custom estimator

```python
# mypkg/budget_plugins.py
from neuroswarm_arm.armora.budget.plugins import register_estimator
from neuroswarm_arm.armora.budget.schemas import ResourceProjection

@register_estimator("kv_vllm")
class VLLMKVEstimator:
    def project_kv(self, *, layers, kv_heads, head_dim, seq_len, batch, elem_size):
        pages_meta = 1.06
        bytes_ = 2 * layers * kv_heads * head_dim * seq_len * batch * elem_size
        return ResourceProjection.single("kv_bytes", bytes_ * pages_meta)
```

Set `NSA_BUDGET_PLUGINS=mypkg.budget_plugins` and `NSA_BUDGET_ESTIMATOR=kv_vllm`.

## Testing plugins

```bash
pytest tests/armora/budget/test_plugins.py -q
```
