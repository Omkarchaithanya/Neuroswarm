---
okf_version: "1.0"
type: agent
id: nexus.agents.research_analyst
title: Research Analyst
description: Long-form synthesis across web and code sources
resource: mcp://agents/research-analyst
tags: [agent, research, synthesis]
aliases: [research-agent, analyst]
namespace: nexus.agents
owners: [platform-team]
visibility: internal
status: approved
lifecycle: stable
priority: 80
token_budget: 1200
token_budget_hard: 2000
mount:
  agents: [research, architect]
  domains: [research]
ontology:
  class: AgentRole
  relations:
    - {pred: uses_tool, obj: nexus.tools.github}
    - {pred: uses_tool, obj: nexus.tools.web_search}
    - {pred: governed_by, obj: nexus.policies.cost_budget}
version: 1.0.0
timestamp: 2026-07-15T00:00:00Z
---

# Research Analyst Agent

## Role

Synthesize findings from web search, GitHub, and institutional playbooks.

## Tools used

- [[nexus.tools.web_search]]
- [[nexus.tools.github]]

## Cascade policy

- Tier 1 for triage
- Tier 2 for synthesis
- Tier 3 for deep reasoning when confidence is low

## See also

- [Research domain](../domains/research/index.md)
- [Cost budget policy](../policies/cost-budget.md)
