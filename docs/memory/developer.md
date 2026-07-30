# Developer guide — Cognitive Memory Runtime

## Layout

```
neuroswarm_arm/runtime/memory/
  api.py          NeuroMemory façade
  service.py      MemoryRuntime orchestrator
  factory.py      build_memory_runtime()
  mem0/           ONLY mem0ai import boundary
  providers/      JsonFallback + IMemoryProvider
  *.py            engines (retrieval, ranking, reflection, …)
```

Legacy shim: `neuroswarm_arm.memory.mem0_client.Mem0Fallback` → wraps `NeuroMemory`.

## Config env

| Env | Default | Meaning |
|-----|---------|---------|
| `NSA_MEM_STORE` | `work/memory` | Root |
| `NSA_MEM_PROVIDER` | `mem0` | `mem0` (default) \| `json` / `fallback` / `emergency` (force json_emergency) \| `auto` |
| `NSA_MEM_LLM` | `local` | `local` \| `openai` \| `none` |
| `NSA_MEM_LLM_BASE_URL` | tier2 URL | OpenAI-compatible base for Mem0 LLM |
| `NSA_MEM_EMBEDDER` | `hash` | `hash` (demo-safe) \| `openai`/`llama` (remote embeddings) |
| `NSA_MEM_QDRANT_PATH` | `{store}/qdrant` | Vector path when Mem0 |
| `NSA_MEM_TOP_K` | `5` | Search limit |
| `NSA_MEM_THRESHOLD` | `0.1` | Mem0 score threshold |
| `NSA_MEM_REFLECTION` | `1` | Post-workflow reflect |
| `NSA_MEM_SAMPLE_PERF` | `1.0` | Perf sink sample rate |

## Add a new typed remember_*

1. Add `MemoryType` + namespace mapping in `namespace.py`
2. Add façade method on `NeuroMemory` in `api.py`
3. Call from the owning kernel (HAOE / RTG / router) — never Mem0 SDK

## Tests

```bash
pytest tests/runtime/memory -q
```

## Providers

- **json** — default Axion-safe offline store
- **mem0** — OSS v3 hybrid retrieval; falls back to json on init failure
