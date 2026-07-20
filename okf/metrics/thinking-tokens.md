---
okf_version: "1.0"
type: metric
id: nexus.metrics.thinking_tokens
title: Thinking Tokens
description: Average reasoning/thinking tokens per request under RTG
tags: [metric, rtg, tokens]
namespace: nexus.metrics
visibility: internal
status: approved
priority: 65
mount:
  agents: [planner, architect]
timestamp: 2026-07-16T00:00:00Z
---

# Thinking Tokens

Governed by RTG + cost policy. Design goal: large reduction vs uncapped reasoning models (~60%). Compare against baseline with RTG disabled.
