# RCIS Developer Guide

## Quick start

```python
from neuroswarm_arm.armora.cost import build_rcis, RequestContext, ObservedRuntimeSignals

rcis = build_rcis()
ctx = RequestContext(
    request_id="req-1",
    execution_id="exec-1",
    model="llama-3b",
    model_tier="tier2",
    backend="llama.cpp",
    quantization="q4_k_m",
    prompt_token_estimate=128,
)
pred = await rcis.predict(ctx)
rcis.open_session(ctx, prediction=pred)
obs = ObservedRuntimeSignals(
    prompt_tokens=128,
    completion_tokens=64,
    cpu_seconds=1.5,
    wall_time_ms=900,
    execution_time_ms=850,
    peak_memory_bytes=2_000_000_000,
    success=True,
)
report = await rcis.finalize(context=ctx, observed=obs, predicted=pred)
print(report.estimated_dollars, report.tokens_per_dollar)
```

## Planner feedback (no DB coupling)

```python
from neuroswarm_arm.armora.cost import WorkloadKey, Objective

choices = await rcis.feedback.lowest_cost_backend(WorkloadKey(intent="chat"))
tier = await rcis.feedback.best_model_tier(Objective.PARETO)
quant = await rcis.feedback.lowest_latency_quant("llama-3b")
```

## Bridge Budget accounting

```python
obs = rcis.from_execution_accounting(accounting_model, context=ctx, extras={...})
```

## Env

- `NSA_RCIS_ENABLED=1`
- `NSA_RCIS_WORK=work/rcis`
- `NSA_RCIS_PERSISTENCE=sqlite|json|duckdb|postgres|parquet`
- `NSA_RCIS_TELEMETRY=prometheus|otel`
- `NSA_RCIS_PLUGINS=my.package.plugins`

## Metrics

Merged into `GET /metrics` via `rcis.export_prometheus()`.
