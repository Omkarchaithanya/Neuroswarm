---
okf_version: "1.0"
type: agent
id: nexus.agents.architect_agent
title: Architect Agent
description: System architecture and kernel-integration agent
resource: mcp://agents/architect-agent
tags: [agent, architect]
aliases: [architect, architect-agent]
namespace: nexus.agents
visibility: internal
status: approved
priority: 85
token_budget: 1200
mount:
  agents: [architect]
  domains: [architecture, planning, deploy]
ontology:
  class: AgentRole
  relations:
    - {pred: governed_by, obj: nexus.policies.cost_budget}
    - {pred: see_also, obj: nexus.architecture.haoe}
    - {pred: see_also, obj: nexus.architecture.dipa}
timestamp: 2026-07-16T00:00:00Z
---

# Architect Agent

Owns cross-layer contracts (HAOE ↔ DIPA ↔ AQR/AWPP/MAKS ↔ OKF). Mounts architecture, deploy, policies, agents catalog, ontology, and playbooks. Prefer progressive disclosure from domain indexes.
