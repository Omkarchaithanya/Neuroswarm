---
okf_version: "1.0"
type: metric
id: nexus.metrics.cascade_hit_rate
title: Cascade Hit Rate
description: Fraction of requests satisfied at tier1 or tier2
tags: [metric, cascade]
namespace: nexus.metrics
visibility: internal
status: approved
priority: 60
mount:
  agents: [planner, architect]
timestamp: 2026-07-15T00:00:00Z
---

# Cascade Hit Rate

Target: >= 0.70 of requests finish without tier3.
