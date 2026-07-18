---
okf_version: "1.0"
type: concept
id: nexus.architecture.dipa
title: DIPA — Disaggregated Inference Proxy for Agents
description: Layer 2 inference runtime kernel; owns backends, ASCR cascade, streaming, recovery
tags: [dipa, layer2, inference]
resource: mcp://dipa
namespace: nexus.architecture
visibility: internal
status: approved
priority: 90
token_budget: 800
mount:
  agents: [architect, planner, coding]
  domains: [architecture]
ontology:
  class: Concept
  relations:
    - {pred: depends_on, obj: nexus.architecture.arm_cascade}
    - {pred: see_also, obj: nexus.architecture.aqr}
    - {pred: see_also, obj: nexus.architecture.awpp}
    - {pred: see_also, obj: nexus.architecture.maks}
    - {pred: see_also, obj: nexus.architecture.haoe}
timestamp: 2026-07-16T00:00:00Z
---

# DIPA

Layer 2 / Plane 3: the **Inference Runtime Kernel**. Agents never call llama.cpp / vLLM / SGLang / ExecuTorch / LiteRT directly — everything flows through DIPA.

## Package

- Code: `neuroswarm_arm.runtime.dipa`
- Factory: `build_dipa(...)`
- Compat: `CascadeRouter` delegates to DIPA

## Lifecycle

Admitted → Planned → Classified → Intent → Model → Backend → Hardware → Policy → Quant(AQR) → Warm(AWPP) → KV(MAKS) → Cascade/Prefill/Decode → Stream → Metrics → Completed

## Subsystems

| Area | Role |
|------|------|
| `router/` | Execution planner, decision/policy |
| `routing/` | Model/backend/quant/topology scoring |
| `cascade/` | Compat shim; production path is ASCR |
| `backends/` | Plugin HAL (llama.cpp, SGLang, vLLM, mock, …) |
| `pd/` | Prefill/decode, KV transfer, chunking |
| `streaming/` | SSE / WS / gRPC / chunked |
| `recovery/` | Retry, circuit breaker, degraded mode |

## Docs

- `/docs/dipa/architecture.md`
- `/docs/dipa/pd-architecture.md`
- ADRs under `/docs/dipa/adr/`
