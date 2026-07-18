---
okf_version: "1.0"
type: concept
id: nexus.architecture.okf_runtime
title: OKF Knowledge OS Runtime
description: Institutional Markdown+YAML knowledge; compiler/runtime over Google OKF format
tags: [okf, knowledge, mem0-separation]
resource: mcp://okf
namespace: nexus.architecture
visibility: internal
status: approved
priority: 85
token_budget: 700
mount:
  agents: [architect, planner, coding]
  domains: [architecture]
ontology:
  class: Concept
  relations:
    - {pred: see_also, obj: nexus.architecture.haoe}
    - {pred: see_also, obj: nexus.architecture.awpp}
    - {pred: see_also, obj: nexus.metrics.okf_token_budget}
timestamp: 2026-07-16T00:00:00Z
---

# OKF Knowledge OS

Google **Open Knowledge Format** = portable Markdown+YAML format.  
NEXUS **Knowledge OS** = compiler/runtime over OKF (mount, rank, budget, navigate).

## Separation (ADR-0002)

| Store | Holds |
|-------|--------|
| Mem0 | User/agent episodic facts |
| OKF | Institutional knowledge (this corpus) |

Never write OKF docs into Mem0.

## Packages

- Format + OS: `packages/okf` (`nexus_okf`)
- Arm facade: `neuroswarm_arm.runtime.okf`
- Env: `NSA_OKF_ROOT`, `NSA_OKF_ARTIFACTS`, `NSA_OKF_TOKEN_BUDGET`, `NSA_OKF_ENABLED`

## CLI

```bash
uv run okf validate --layer both
uv run okf build --source okf --strict
uv run okf query "cascade policy" --agent architect
```

## Chat path

`mem0_recall → okf_context → semantic_route → okf_tool_docs → …`

## Docs

- `/docs/okf/README.md`
- `/docs/okf/SPEC_COMPLIANCE.md`
- `/docs/okf/adr/`
