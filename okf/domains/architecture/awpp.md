---
okf_version: "1.0"
type: concept
id: nexus.architecture.awpp
title: AWPP — Agentic Workload Pre-warm Predictor
description: Frequency/Markov predictive pre-warm on Arm under a 1% CPU budget
tags: [awpp, prewarm, layer4, markov]
resource: mcp://awpp
namespace: nexus.architecture
visibility: internal
status: approved
priority: 75
token_budget: 700
mount:
  agents: [architect, planner]
  domains: [architecture]
ontology:
  class: Concept
  relations:
    - {pred: depends_on, obj: nexus.architecture.dipa}
    - {pred: see_also, obj: nexus.architecture.okf_runtime}
    - {pred: uses_tool, obj: nexus.architecture.okf_runtime}
timestamp: 2026-07-20T00:00:00Z
---

# AWPP

Agentic Workload Pre-warm Predictor (Layer 4): predicts the next model/tool/memory
targets and warms them before DIPA decode. **Phase 1 on Axion is frequency/Markov
predictive pre-warm under `NSA_AWPP_MAX_CPU_FRACTION=0.01` — not trained PPO/GEPA.**

GEPA remains AROP text evolution. Do not claim “PPO/GEPA AWPP” until a policy
artifact + eval numbers exist (Phase 2 offline from `work/awpp/replay/`).

## Hot path

1. DIPA lifecycle step **Warm(AWPP)** → `PredictiveWarmConnector.ensure_warm`
2. Build `AWPPState` from request (agent/session, prompt excerpt, last tools)
3. `MarkovPolicy` / `FrequencyPolicy` (default `NSA_AWPP_ACTIVE_POLICY=markov`);
   fallback `ACRPrefetchPredictor` → `MemoryPrefetchPredictor`
4. Confidence gate (`NSA_AWPP_CONFIDENCE_THRESHOLD`)
5. `WarmerDispatcher` → Model / Memory / Tool warmers (+ MAKS KV via heuristic)
6. On inference complete: `Observation` → policy.update + JSONL replay

## Package

| Piece | Path |
| --- | --- |
| Connector | `neuroswarm_arm.runtime.dipa.awpp.PredictiveWarmConnector` |
| Heuristic fallback | `HeuristicWarmConnector` |
| Policies | `runtime.awpp.policy` (markov / frequency) |
| Warmers | `runtime.awpp.warmers` |
| Config | `NSA_AWPP_*` via `runtime.awpp.config` |
| OKF adapter | `runtime.okf.connectors.awpp_okf.AWPPOkfAdapter` |

## Honesty (Axion)

- Model warm is best-effort HTTP `/health` (page touch) — not GPU weight residency.
- CPU budget is enforced (`awpp_budget_skips_total`, `awpp_cpu_time_ms`).
- `/health` reports `awpp: {policy, warm_hits, skips, ...}`.

## Integration

- Chat DAG mounts OKF before cascade; AWPP may pre-fetch topic docs / Mem0 hits
- Never stores institutional OKF text in Mem0 (ADR-0002)
- AQR `RequestContext.awpp_prediction` / `model_warm_state` feed `WarmBonusExtractor`
