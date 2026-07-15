---
okf_version: "1.0"
type: policy
id: nexus.policies.cost_budget
title: Cost Budget Policy
description: Per-request USD and token ceilings for agent workflows
tags: [policy, cost, budget]
aliases: [cost-budget]
namespace: nexus.policies
visibility: internal
status: approved
priority: 90
token_budget: 250
mount:
  agents: [research, planner, coding, reviewer, architect]
timestamp: 2026-07-15T00:00:00Z
---

# Cost Budget Policy

## Limits

- Default request budget: `$0.05`
- OKF context soft budget: `1200` tokens
- Tool documentation loaded only after MCP routing

## Enforcement

RTG consumes projected OKF tokens. Exceeding hard budget truncates lowest-ranked sections.
