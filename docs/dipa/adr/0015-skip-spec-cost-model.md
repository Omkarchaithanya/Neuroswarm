# ADR 0015: Skip-Spec Cost Model

## Status

Accepted

## Context

Speculative draft+verify adds a draft forward even when historical acceptance is low or the latency SLA is nearly exhausted. Vision workloads already use a heavy prefill path. Fixed speculation wastes cycles and can bust tight SLAs.

## Decision

1. Add `neuroswarm_arm/runtime/armcascade/policies/cost_model.py` with `should_skip_spec(plan, signals) -> (bool, reason)`.
2. Skip when any of:
   - `historical_acceptance < NSA_ASCR_SKIP_HISTORICAL_MIN` (default 0.3) → `hist`
   - `latency_used_ms / latency_budget_ms > NSA_ASCR_SKIP_PRESSURE_MAX` (default 0.8) → `pressure`
   - `max_tokens < NSA_ASCR_SKIP_MAX_TOKENS_MIN` (default 8) → `short`
   - `workload == VISION` → `vision`
3. `DefaultCascadePolicyEngine.apply(plan, signals)` mutates `plan.speculation=False` when skip fires; `ASCREngine.run` calls apply before the propose/verify loop and increments `ascr_skip_spec_total{reason=...}`.
4. Master gate: `strategies.cost_model.enabled: false` + `NSA_ASCR_COST_MODEL_ENABLED=0` (safe default). Disabled → never skip.

## Consequences

- Tight-SLA / low-ROI requests fall through to quality cascade without a wasted draft call.
- Fully reversible via feature flag; no change to Leviathan accept math.
- Thresholds calibrated for Axion cascade SLAs; see `docs/armcascade/cost-model.md`.
