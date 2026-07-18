---
okf_version: "1.0"
type: metric
id: nexus.metrics.gateway_p95
title: Gateway P95 Latency
description: End-to-end p95 latency for /v1/chat/completions on Axion
tags: [metric, latency, gateway]
namespace: nexus.metrics
visibility: internal
status: approved
priority: 70
mount:
  agents: [planner, architect]
timestamp: 2026-07-16T00:00:00Z
---

# Gateway P95 Latency

Measure chat completion latency at gateway (includes HAOE + DIPA cascade). Scrape Prometheus / Grafana panels under `ops/`. Capture with `capture-evidence.sh` on Axion demos.
