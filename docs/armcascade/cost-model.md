# ASCR Cost Model (G15)

## Purpose

Decide **when not to speculate**. Draft+verify only pays off when acceptance history is healthy, the latency budget has headroom, and the generation is long enough to amortize the draft call.

## Trade-off

| Speculate | Skip |
|-----------|------|
| Extra draft forward; hope for multi-token accept | No draft call; quality-cascade / full generate |
| Wins when historical accept ≳ 0.3 and SLA pressure &lt; 0.8 | Wins when draft ROI is poor or SLA already tight |
| Vision prefill already heavy — draft adds little | Vision always skips |

Skipping too aggressively lowers effective TPS on easy prompts. Speculating under pressure busts `latency_sla_ms`.

## Signals

Built in `ASCREngine.run` as `CostSignals`:

- `historical_acceptance` — EMA of prior ASCR accepts (`ASCREngine._history_accept`)
- `latency_used_ms` / `latency_budget_ms` — wall time so far vs `req.latency_sla_ms`
- `max_tokens` — from `InferenceRequest` (plan has no `max_tokens` field)
- `workload` — `ExecutionPlan.workload` (`WorkloadClass`)

## Thresholds (calibration)

Defaults mirror `strategies.cost_model` and `.env.example`:

| Env | Default | Rationale |
|-----|---------|-----------|
| `NSA_ASCR_COST_MODEL_ENABLED` | `0` | Reversible; off in production until measured |
| `NSA_ASCR_SKIP_HISTORICAL_MIN` | `0.3` | Below ~30% accept, draft call rarely saves a target forward |
| `NSA_ASCR_SKIP_PRESSURE_MAX` | `0.8` | Leave ≥20% SLA for verify/generate; draft would often miss deadline |
| `NSA_ASCR_SKIP_MAX_TOKENS_MIN` | `8` | Short gens cannot amortize draft RTT |

Vision always skips: prefill-dominated path; speculative decode ROI is weak.

Calibration method: unit table in `tests/runtime/armcascade/test_skip_spec.py` + live `scripts/probe-ascr-speculation.py` comparing `cascade_latency_ms` / `ascr_skip_spec_total{reason=*}` under synthetic pressure.

## Metrics

- `ascr_skip_spec_total` — aggregate counter
- `ascr_skip_spec_total{reason=hist|pressure|short|vision}` — labeled key form (flat local store)

## Related

- ADR [0015-skip-spec-cost-model](../dipa/adr/0015-skip-spec-cost-model.md)
- Top-τ truncation (G14): [0014-top-tau-truncation](../dipa/adr/0014-top-tau-truncation.md)
