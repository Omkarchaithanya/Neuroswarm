---
okf_version: "1.0"
type: concept
id: nexus.architecture.router
title: Semantic MCP Tool Router
description: Top-K tool schema selection via embeddings + TurboVec; post-route OKF tool docs
tags: [router, mcp, semantic, turbovec]
resource: mcp://router
namespace: nexus.architecture
visibility: internal
status: approved
priority: 85
token_budget: 700
mount:
  agents: [architect, coding, research]
  domains: [architecture]
ontology:
  class: Concept
  relations:
    - {pred: see_also, obj: nexus.architecture.haoe}
    - {pred: see_also, obj: nexus.architecture.okf_runtime}
    - {pred: see_also, obj: nexus.metrics.tool_schema_reduction}
timestamp: 2026-07-16T00:00:00Z
---

# Semantic MCP Tool Router

Replaces naïve injection of all MCP tool schemas with Top-K semantic routing:

`BGE-small → TurboVec → hybrid retrieval → rerank → Top-K schemas → DIPA`

## Package

- Code: `neuroswarm_arm.runtime.router`
- Docs: `neuroswarm_arm/runtime/router/docs/`

## Policy (ADR-0003)

1. Semantic route selects tools (schemas only)
2. **Then** load OKF tool docs for those IDs (`load_tool_docs_after_route`)
3. Never dump full tool catalog into the prompt

## Chat DAG position

`mem0_recall → okf_context → semantic_route → okf_tool_docs → … → DIPA`

## Benchmarks

```bash
pytest tests/runtime/router -q
python benchmarks/router_full.py
```

## Docs

- `neuroswarm_arm/runtime/router/docs/architecture.md`
- `neuroswarm_arm/runtime/router/docs/deployment.md`
- `/docs/okf/adr/0003-tool-docs-after-route.md`
