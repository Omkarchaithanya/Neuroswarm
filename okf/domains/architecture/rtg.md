---
okf_version: "1.0"
type: concept
id: nexus.architecture.rtg
title: RTG — Reasoning Token Governor
description: Caps thinking tokens using tool confidence and hardware-aware budgets
tags: [rtg, governor, tokens]
resource: mcp://rtg
namespace: nexus.architecture
visibility: internal
status: approved
priority: 80
token_budget: 600
mount:
  agents: [architect, planner]
  domains: [architecture]
ontology:
  class: Concept
  relations:
    - {pred: governed_by, obj: nexus.policies.cost_budget}
    - {pred: see_also, obj: nexus.architecture.router}
    - {pred: see_also, obj: nexus.metrics.thinking_tokens}
timestamp: 2026-07-16T00:00:00Z
---

# RTG

Reasoning Token Governor: cuts unnecessary thinking tokens on reasoning models by tying budgets to tool-route confidence and hardware policy.

## Package

- Code: `neuroswarm_arm.runtime.rtg`
- Config: `neuroswarm_arm/runtime/rtg/config/` (`policy.yaml`, `budgets.yaml`, `thresholds.yaml`, `hardware.yaml`)
- OKF connector: `neuroswarm_arm.runtime.okf.connectors.rtg_budget` → reports `okf_tokens` in baggage

## Responsibilities

- Soft/hard ceilings on thinking tokens per request
- Escalate or clamp when router confidence is high (tools already selected)
- Feed cost policy (`policies/cost-budget.md`)

## Docs

- `/docs/rtg/00-research.md`
- `/docs/rtg/01-architecture.md`
- `/docs/rtg/03-hackathon.md`
- `/docs/budget/`
