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

In-process registry that replaces naïve injection of all MCP tool schemas with Top-K semantic routing (**not** a transparent MCP proxy):

`nomic-embed-text-v1.5 (33.4M, 384-dim) → TurboVec (default 4-bit) → hybrid → rerank → Top-K schemas → DIPA`

## Honest defaults

| Claim | Value |
|-------|-------|
| Encoder | nomic-embed-text-v1.5 — **384-dim**, ~33.4M params via **FastEmbed** default |
| TurboVec | **4-bit** TurboQuant when tools ≥ `NSA_ROUTER_TURBOVEC_MIN_TOOLS` (default **0**); else exact float32 |
| Expand / re-rank trigger | `NSA_ROUTER_THRESHOLD` / `NSA_ROUTER_RERANK_TRIGGER` = **0.42** |
| High-confidence gate | `NSA_ROUTER_HIGH_CONF_GATE` = **0.70** → caps thinking budget (FastEmbed-calibrated) |
| Live catalog | **≥40** per-tool schemas under `templates/mcp-servers/*/tools/` |

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
uv run python benchmarks/router_mcpga.py
python benchmarks/router_full.py
```

## Docs

- `neuroswarm_arm/runtime/router/docs/architecture.md`
- `neuroswarm_arm/runtime/router/docs/deployment.md`
- `/docs/okf/adr/0003-tool-docs-after-route.md`
