---
okf_version: "1.0"
type: concept
id: nexus.architecture.maks
title: MAKS — Multi-Agent KV-Cache Sharing
description: Layer 5 KV memory OS; capability-aware sharing without cross-model assumptions
tags: [maks, kv, layer5, memory]
resource: mcp://maks
namespace: nexus.architecture
visibility: internal
status: approved
priority: 80
token_budget: 700
mount:
  agents: [architect, coding]
  domains: [architecture]
ontology:
  class: Concept
  relations:
    - {pred: depends_on, obj: nexus.architecture.dipa}
    - {pred: see_also, obj: nexus.architecture.arm_cascade}
timestamp: 2026-07-16T00:00:00Z
---

# MAKS

Multi-Agent KV-Cache Sharing: NEXUS **Layer 5** memory OS for sessions and prefix reuse. Distinct from Plane 5 (AROP).

## Package

- Code: `neuroswarm_arm.runtime.maks`
- Docs: `/docs/maks/`

## Capabilities (Axion-honest)

Cross-model reuse is **never** assumed. Adapt via CapabilityRegistry:

| Mode | When |
|------|------|
| paged | backend supports paged KV |
| prefix | prefix reuse only |
| opaque | session blob fallback |

## Query

```text
maks.capability_matrix()
GET /maks/capabilities
```

## Integration

DIPA lifecycle step: **KV(MAKS)** before cascade/prefill/decode. Dedup targets measured via metrics (see `kv-dedup-ratio`).

## Docs

- `/docs/maks/capability-matrix.md`
- `/docs/maks/roadmap.md`
- `/docs/maks/extension-mte-cxl.md`
