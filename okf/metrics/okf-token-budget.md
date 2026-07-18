---
okf_version: "1.0"
type: metric
id: nexus.metrics.okf_token_budget
title: OKF Token Budget
description: Tokens consumed stitching institutional OKF context per request
tags: [metric, okf, budget]
namespace: nexus.metrics
visibility: internal
status: approved
priority: 65
mount:
  agents: [planner, architect]
timestamp: 2026-07-16T00:00:00Z
---

# OKF Token Budget

Soft ceiling: `NSA_OKF_TOKEN_BUDGET` (default ~1200).  
Reported via RTG baggage as `okf_tokens`. Prefer progressive disclosure over dumping domains.
