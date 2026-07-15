# Cognitive Memory Runtime — Architecture

Provider-agnostic **episodic / agent memory** for NeuroSwarm-Arm. Mem0 OSS v3 is one backend; business code uses only `NeuroMemory`.

For the full Context Operating System (understanding → plan → compress → assemble), see [docs/acr](../acr/README.md) — ACR wraps this runtime + OKF.

## Memory planes (do not merge)

| Plane | Package | Role |
|-------|---------|------|
| Cognitive / episodic | `neuroswarm_arm.runtime.memory` | Facts, tools, reflections, cost, performance |
| Institutional | OKF (`nexus_okf`) | Git-native knowledge — [ADR-0002](../okf/adr/0002-mem0-okf-separation.md) |
| Inference KV | `neuroswarm_arm.runtime.kv` + MAKS | Token KV blocks, not conversation memory |

Merge Mem0 facts + OKF text **only at prompt assembly** (`merge_mem0_okf`).

## Component diagram

```mermaid
flowchart TB
  subgraph facade [Public API]
    NM[NeuroMemory api.py]
  end
  subgraph runtime [MemoryRuntime service.py]
    RET[retrieval]
    RANK[ranking]
    IMP[importance]
    REF[reflection]
    COMP[compression]
    PRED[predictor]
  end
  subgraph port [IMemoryProvider]
    M0[mem0/Mem0Provider]
    JS[JsonFallbackProvider]
  end
  NM --> runtime --> port
  M0 -->|only here| SDK[mem0ai SDK v3]
```

## Chat sequence

```mermaid
sequenceDiagram
  participant GW as AgentGateway
  participant HAOE as HAOE chat DAG
  participant NM as NeuroMemory
  participant OKF as OKF
  participant DIPA as DIPA
  GW->>HAOE: submit_workflow chat
  HAOE->>NM: recall + reflection/
  HAOE->>OKF: query institutional
  HAOE->>DIPA: cascade
  HAOE->>NM: remember_* + reflect
```

## Lifecycle

```mermaid
stateDiagram-v2
  [*] --> Created: remember_*
  Created --> Ranked: importance + hybrid retrieve
  Ranked --> Promoted: high importance
  Ranked --> Compressed: merge duplicates
  Ranked --> Archived: low importance / TTL
  Archived --> Deleted: forget policy
  Created --> Reflected: post-workflow reflect
```

## Namespaces

`users/` `agents/` `workflows/` `tools/` `benchmarks/` `prompts/` `system/` `swarm/` `reflection/` `reasoning/` `performance/` `cost/` `planner/` `router/` `execution/` `latency/` `evolution/`

## Mem0 v3 constraints

- ADD-only extraction (no in-place UPDATE/DELETE merge)
- `search(..., filters={"user_id": ...})` — entity IDs inside `filters`
- No `enable_graph` / Neo4j — entity linking is built-in; app graph is `graph.py`
- Install: `mem0ai[nlp]` + spaCy when Python ≤3.12; else semantic-only / JSON provider
