---
okf_version: "1.0"
type: concept
id: nexus.architecture.awpp
title: AWPP — Agentic Workload Pre-warm Predictor
description: Predicts and pre-warms models/contexts to cut cold-start latency
tags: [awpp, prewarm, layer4]
resource: mcp://awpp
namespace: nexus.architecture
visibility: internal
status: approved
priority: 75
token_budget: 600
mount:
  agents: [architect, planner]
  domains: [architecture]
ontology:
  class: Concept
  relations:
    - {pred: depends_on, obj: nexus.architecture.dipa}
    - {pred: see_also, obj: nexus.architecture.okf_runtime}
    - {pred: uses_tool, obj: nexus.architecture.okf_runtime}
timestamp: 2026-07-16T00:00:00Z
---

# AWPP

Agentic Workload Pre-warm Predictor: reduces cold starts by predicting which models/topics to warm. DIPA asks AWPP via connectors.

## Package

- Runtime connector: `neuroswarm_arm.runtime.okf.connectors.awpp_okf.AWPPOkfAdapter`
- Contract: `load_index()` / `load_topic(path)` over OKF progressive disclosure

## Responsibilities

- Predict next workload from Mem0 patterns + OKF indexes
- Pre-warm model/backend slots before DIPA decode path
- Feed warm-pool signals into DIPA lifecycle step **Warm(AWPP)**

## Integration

- Chat DAG mounts OKF before cascade; AWPP may pre-fetch topic docs
- Never stores institutional OKF text in Mem0 (ADR-0002)

## Docs

See DIPA lifecycle and OKF runtime connector notes under `/docs/okf/` and `/docs/dipa/`.
