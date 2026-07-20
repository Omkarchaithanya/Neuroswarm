---
okf_version: "1.0"
type: concept
id: nexus.architecture.haoe
title: HAOE — Heterogeneous Agentic Orchestration Engine
description: Layer 1 agent runtime kernel; coordinates workflows, never runs inference
tags: [haoe, layer1, orchestration]
resource: mcp://haoe
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
    - {pred: depends_on, obj: nexus.architecture.dipa}
    - {pred: see_also, obj: nexus.playbooks.chat_cascade}
    - {pred: see_also, obj: nexus.architecture.okf_runtime}
timestamp: 2026-07-16T00:00:00Z
---

# HAOE

Layer 1 / Plane 4 of NEXUS-ARM: the **agent runtime kernel**. Every request executes through HAOE. HAOE coordinates inference via DIPA; it never performs inference and never imports backend clients.

## Package

- Code: `neuroswarm_arm.runtime.haoe`
- Factory: `build_haoe(...)`
- Facade: `neuroswarm_arm.router.HAOEScheduler` (compat alias)

## Responsibilities

- Workflow planning (`plan_chat`) → TaskGraph
- Work stealing, priority scheduling, affinity HAL
- Semantic route + KV session orchestration (via handlers)
- Telemetry / HAOE metrics
- Safe Axion fallbacks (no NUMA/MTE/CXL assumptions)

## Chat path (summary)

`API → HAOE.submit_workflow(chat) → plan → execute → semantic_route → kv_session → dipa_infer → checkpoint → ChatResponse`

## Docs

- `/docs/haoe/architecture.md`
- ADRs under `/docs/haoe/adr/`
