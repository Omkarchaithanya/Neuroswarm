# RCIS Lifecycle

## Phases

1. **Predict** — `RuntimeCostIntelligence.predict(RequestContext)` stores `CostPrediction`
2. **Open** — `open_session` creates mutable `CostSession`
3. **Execute** — DIPA/HAOE run inference (unchanged ownership)
4. **Observe** — tokens, KV, speculation, CPU, memory, energy
5. **Estimate** — `LiveCostBreakdown` from configurable rates
6. **Analyze** — build immutable `RuntimeCostReport` + prediction errors
7. **Persist** — write report to configured store
8. **Telemetry** — emit `runtime_*` Prometheus / OTel
9. **Feedback** — repositories answer planner queries later

## Dual output

```python
response = gateway.handle_chat(req)           # ExecutionResult fields
report = response.runtime_cost_report         # RuntimeCostReport dict
```

## Sequence

See [diagrams.md](diagrams.md).
