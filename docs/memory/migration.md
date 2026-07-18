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
# Lean gateway image already includes mem0ai via uv group `gateway`.
# For local NLP extras: uv sync --group nlp
```

### Axion Compose demo (fact extraction)

Default Axion stays `NSA_MEM_LLM=none` (stable, hash ingest). For a live extraction demo:

```bash
# on VM:
PRODUCT_DEMO=1 bash scripts/remote-compose-up.sh
# or manually:
export NSA_MEM_LLM=local
export NSA_MEM_LLM_BASE_URL=http://tier2:8080
export NSA_MEM_EMBEDDER=hash   # hash vectors; tier LLM extracts facts
export TIER2_CTX=8192          # Mem0 v3 default prompt needs headroom; we also install a lean prompt
docker compose up -d --force-recreate tier2 gateway
# then: bash scripts/axion-product-verify.sh
# Expect /health memory.provider=mem0 and non-empty recall after chat remember.
```

`NSA_MEM_EMBEDDER=hash` avoids requiring llama `--embeddings`. Typed `remember_fact` uses `infer=False`; chat `remember(messages)` uses lean extraction + fallback.

## ADR

OKF and cognitive memory remain separate stores ([ADR-0002](../okf/adr/0002-mem0-okf-separation.md)).
