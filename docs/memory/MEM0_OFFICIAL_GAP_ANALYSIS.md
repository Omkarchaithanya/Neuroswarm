# Mem0 Official Gap Analysis (NEXUS Layer 4)

Validation date: 2026-07-15

## Official sources

- https://github.com/mem0ai/mem0
- https://docs.mem0.ai/open-source/overview
- https://docs.mem0.ai/migration/oss-v2-to-v3
- Mem0 v3: ADD-only extraction, hybrid retrieval (semantic + BM25 + entity), built-in entity linking (no Neo4j)

## Philosophy

**Mem0 IS:** memory layer (extract → embed → store → hybrid search → inject).

**Mem0 IS NOT:** vector DB product, RAG framework, prompt manager, orchestrator, OKF, KV/MAKS, hardware topology.

## Classification legend

- Matches Official Mem0
- Compatible Extension (NEXUS on top)
- Incorrect (violates philosophy)
- Missing

## Module gap table

| Module / behavior | Status | Why |
|-------------------|--------|-----|
| Sole `mem0ai` import boundary | Matches | Correct isolation |
| `search(..., filters={user_id})` | Matches | OSS v3 contract |
| No Neo4j / `enable_graph` | Matches | v3 entity linking |
| ADR-0002 Mem0 vs OKF | Matches | Separate stores |
| ACR wraps memory, no storage ownership | Matches | Context OS pattern |
| Typed `remember_*` + namespaces as metadata | Compatible Extension | Maps to Mem0 entries + metadata |
| Post-retrieval importance/TTL/cache | Compatible Extension | App policy after Mem0 search |
| Reflection/prediction storing via Mem0 | Compatible Extension | Must call adapter.add |
| ACR compression after retrieve | Compatible Extension | Compression ≠ memory engine |
| Hardware outside Mem0 | Matches | KV/MAKS/ACR hardware |
| Default provider = `json` | Incorrect | Bypasses Mem0 |
| JsonFallback as primary store | Incorrect | Parallel memory DB |
| Chat without `add(messages)` | Incorrect / partial | Official loop requires message extraction |
| Custom `graph.py` as Mem0 graph | Incorrect | Duplicates entity linking |
| Ranking as primary hybrid scorer | Incorrect if pre-Mem0 | Hybrid belongs inside Mem0 |
| Hash embeddings for production | Incorrect | Mem0 owns embeddings |
| Mem0Adapter façade | Missing | Needed thin wrap |
| ARMORA → adapter path | Missing | sinks unwired |
| Module→Mem0 mapping docs | Missing | This doc + MAPPING.md |
| Official search→assemble→add(messages) | Partial / Missing | Typed write-back only |

## Target architecture

```text
HAOE/ACR/ARMORA/RTG
    → NeuroMemory / Mem0Adapter
        → mem0.Memory (official SDK)
OKF stays separate (merge at prompt only)
```

## Remediation (executed in alignment refactor)

1. Mem0Adapter wraps official SDK only
2. Default provider = mem0; JSON = emergency circuit-breaker
3. Chat: search then add(messages)
4. Custom graph demoted; ranking = post-Mem0 policy only
5. Package layout: adapter/ service/ retrieval/ …
