---
okf_version: "1.0"
type: metric
id: nexus.metrics.kv_dedup_ratio
title: KV Dedup Ratio
description: Shared KV reuse ratio across concurrent agent sessions (MAKS)
tags: [metric, maks, kv]
namespace: nexus.metrics
visibility: internal
status: approved
priority: 60
mount:
  agents: [planner, architect]
timestamp: 2026-07-16T00:00:00Z
---

# KV Dedup Ratio

Fraction of KV pages/prefixes reused via MAKS vs duplicated per session. Cross-model reuse never assumed. Design band: 40–70% when capability matrix allows sharing.
