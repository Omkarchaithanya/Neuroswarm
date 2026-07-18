---
okf_version: "1.0"
type: agent
id: nexus.agents.planner_agent
title: Planner Agent
description: Task decomposition and deploy/runbook planning agent
resource: mcp://agents/planner-agent
tags: [agent, planner]
aliases: [planner, planner-agent]
namespace: nexus.agents
visibility: internal
status: approved
priority: 75
token_budget: 1000
mount:
  agents: [planner, architect]
  domains: [planning, deploy]
ontology:
  class: AgentRole
  relations:
    - {pred: governed_by, obj: nexus.policies.cost_budget}
    - {pred: see_also, obj: nexus.playbooks.deploy_axion}
timestamp: 2026-07-16T00:00:00Z
---

# Planner Agent

Decomposes work into ordered steps. Mounts planning + deploy domains, policies, playbooks, and metrics. Prefer Axion Compose playbooks for demos; Helm for cluster packaging.
