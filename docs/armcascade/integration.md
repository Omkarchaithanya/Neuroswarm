# ASCR Integration Guide

## DIPA

`build_dipa()` constructs `ASCREngine` via `build_ascr()`. `ExecutionPipeline` unchanged — still calls `cascade_engine.run()`.

`SpeculationRouter` writes strategy / draft_len / graph into `ExecutionPlan.metadata["speculation"]`.

## Peer layers (connectors only)

| Peer | ASCR use |
|------|----------|
| HAOE | Calls DIPA; never imports ASCR concretes |
| ARMORA | `model="cascade"` → DIPA → ASCR |
| AQR | Quant on plan; optional `aqr_prefer_fast` hint |
| AWPP | Warm before cascade phase |
| MAKS | `kv_handle` into propose/verify |
| RTG | Token caps + post-hoc escalate re-entry |
| Mem0 / OKF | Context in prompt; graph may include `memory` node |
| Performix | `PerformixHook.record()` observations for future evolution |

## PD interaction

When `NSA_DIPA_PD_MODE=soft|native` and long prompts, DecisionEngine may disable cascade — ASCR not invoked (existing behavior).
