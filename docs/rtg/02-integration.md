# RTG Integration & Migration

## Wiring

1. `build_rtg(kv_pressure=..., semantic_router=..., metrics_bridge=...)`
2. `DIPAReasoningHook(rtg)` implements `IReasoningHook`
3. `build_dipa(reasoning_hook=hook)`
4. `ReasoningGovernor(rtg=rtg)` keeps CascadeRouter / bench API

## Migration

| Before | After |
|--------|-------|
| `ReasoningGovernor().cap(plan)` static | Same API → RTG `initial_budget` |
| No mid-decode control | `on_chunk` / `on_complete` in pipeline |
| Metrics: `neuroswarm_last_thinking_token_cap` | Plus `rtg_*` series |

Legacy heuristic path remains if `rtg=None` or `NSA_RTG_ENABLED=0`.

## Non-goals (do not duplicate)

- HAOE task scheduling
- AQR quant selection (hints only via `governor_accuracy_demand`)
- MAKS eviction / share
- Cascade tier execution (escalate hint only)

## Tests

```bash
pytest tests/runtime/rtg -q
python benchmarks/rtg_suite.py
```
