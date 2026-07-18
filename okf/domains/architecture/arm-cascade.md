---
okf_version: "1.0"
type: concept
id: nexus.architecture.arm_cascade
title: ArmCascade / ASCR
description: Adaptive Speculative Cascade Runtime — CPU-CPU draft/verify/escalate on Arm
tags: [armcascade, ascr, cascade, speculative]
resource: mcp://armcascade
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
    - {pred: see_also, obj: nexus.architecture.dipa}
    - {pred: see_also, obj: nexus.metrics.cascade_hit_rate}
    - {pred: see_also, obj: nexus.playbooks.chat_cascade}
timestamp: 2026-07-16T00:00:00Z
---

# ArmCascade / ASCR

**ASCR** (Adaptive Speculative Cascade Runtime) is the production cascade path. Former heuristic Speculative Cascade Router is a compat shim under DIPA `cascade/`.

## Package

- Code: `neuroswarm_arm.runtime.armcascade`
- Config: `neuroswarm_arm/runtime/armcascade/config/` (`tiers.yaml`, `strategies.yaml`, `escalation_graphs.yaml`, `ascr.yaml`)

## Tier sketch (MVP)

| Tier | Role | Typical model |
|------|------|----------------|
| 1 | Draft | 0.5B Q4 |
| 2 | Verify | 3B Q5 |
| 3 | Arbiter | 8B Q5 |

## Flow

`propose → verify → escalate` under DIPA; HAOE never runs models.

## Metrics

- Cascade hit rate (tier1/tier2 finish without tier3)
- Target: >= 0.70 — see `/metrics/cascade-hit-rate.md`

## Docs

- `/docs/armcascade/`
- `/docs/dipa/adr/0008-ascr-replaces-heuristic-cascade.md` (if present)
- `/docs/armcascade/Architecture.md`
