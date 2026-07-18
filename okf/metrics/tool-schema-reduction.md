---
okf_version: "1.0"
type: metric
id: nexus.metrics.tool_schema_reduction
title: Tool Schema Reduction
description: Fraction of MCP schema tokens avoided by Top-K semantic routing
tags: [metric, router, mcp]
namespace: nexus.metrics
visibility: internal
status: approved
priority: 70
mount:
  agents: [planner, architect, coding]
timestamp: 2026-07-16T00:00:00Z
---

# Tool Schema Reduction

Target: large cut vs injecting all tool schemas (design goal ~92%).  
Measure: tokens of selected Top-K schemas / tokens of full catalog. Benchmark via `benchmarks/router_full.py`.
