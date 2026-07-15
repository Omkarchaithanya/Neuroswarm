---
okf_version: "1.0"
type: agent
id: nexus.agents.coding_agent
title: Coding Agent
description: Implementation and repository navigation agent
resource: mcp://agents/coding-agent
tags: [agent, coding]
aliases: [coder, coding-agent]
namespace: nexus.agents
visibility: internal
status: approved
priority: 75
token_budget: 1000
mount:
  agents: [coding, architect]
  domains: [coding]
ontology:
  class: AgentRole
  relations:
    - {pred: uses_tool, obj: nexus.tools.github}
    - {pred: governed_by, obj: nexus.policies.cost_budget}
timestamp: 2026-07-15T00:00:00Z
---

# Coding Agent

Implements features against NEXUS-ARM kernels. Mounts coding domain and GitHub tool docs only after routing.
