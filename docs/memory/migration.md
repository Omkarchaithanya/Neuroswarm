# Migration guide — Mem0Fallback → NeuroMemory

## What changed

| Before | After |
|--------|-------|
| `Mem0Fallback` JSON token-overlap | `NeuroMemory` + `IMemoryProvider` |
| `memory.add(agent, fact)` | `neuro.remember_*` or shim `add` |
| `memory.search(agent, q)` | `neuro.recall` / `search` |
| Direct `mem0ai` (unused) | Only in `runtime/memory/mem0/` |

## Compat

`build_memory(root)` still returns `Mem0Fallback`, now backed by `NeuroMemory`. Existing HistoryRanker / HAOE call sites keep working.

Prefer:

```python
from neuroswarm_arm.runtime.memory import build_memory_runtime
mem = build_memory_runtime(cfg.mem_store)
```

## Mem0 OSS v3

```python
# search entity IDs must be in filters
m.search("q", filters={"user_id": "alice"}, top_k=5, threshold=0.1)
# add is ADD-only — no UPDATE/DELETE events
```

Enable real Mem0:

```bash
set NSA_MEM_PROVIDER=mem0
set NSA_MEM_LLM=local   # or openai
pip install "mem0ai[nlp]" fastembed
```

## ADR

OKF and cognitive memory remain separate stores ([ADR-0002](../okf/adr/0002-mem0-okf-separation.md)).
