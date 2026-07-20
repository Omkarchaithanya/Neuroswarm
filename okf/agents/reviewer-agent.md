---
okf_version: "1.0"
type: agent
id: nexus.agents.reviewer_agent
title: Reviewer Agent
description: Quality, security, and cost-policy review agent
resource: mcp://agents/reviewer-agent
tags: [agent, review]
aliases: [reviewer, reviewer-agent]
namespace: nexus.agents
visibility: internal
status: approved
priority: 70
token_budget: 1000
mount:
  agents: [reviewer]
  domains: [review]
ontology:
  class: AgentRole
  relations:
    - {pred: governed_by, obj: nexus.policies.cost_budget}
    - {pred: uses_tool, obj: nexus.tools.github}
timestamp: 2026-07-16T00:00:00Z
---

# Reviewer Agent

Reviews diffs and runtime evidence against cost, security, and cascade SLIs. Mounts review domain, policies, and playbooks. Prefer GitHub MCP after semantic routing for PR context.
