# Package layout (logical → physical)

Plan target directories map to these modules (Python keeps flat modules to avoid
``api.py`` / ``api/`` shadow collisions). Sole SDK boundary is ``adapter/``.

| Plan dir | Physical module |
|----------|-----------------|
| adapter/ | [`adapter/`](../../neuroswarm_arm/runtime/memory/adapter/) — **only** `mem0ai` import |
| api/ | [`api.py`](../../neuroswarm_arm/runtime/memory/api.py) — NeuroMemory |
| service/ | [`service.py`](../../neuroswarm_arm/runtime/memory/service.py) |
| retrieval/ | [`retrieval.py`](../../neuroswarm_arm/runtime/memory/retrieval.py) |
| ranking/ | [`ranking.py`](../../neuroswarm_arm/runtime/memory/ranking.py) — post-Mem0 policy only |
| compression/ | [`compression.py`](../../neuroswarm_arm/runtime/memory/compression.py) |
| cache/ | [`cache.py`](../../neuroswarm_arm/runtime/memory/cache.py) |
| schemas/ | [`schemas.py`](../../neuroswarm_arm/runtime/memory/schemas.py) |
| reflection/ | [`reflection.py`](../../neuroswarm_arm/runtime/memory/reflection.py) |
| prediction/ | [`predictor.py`](../../neuroswarm_arm/runtime/memory/predictor.py) |
| namespaces/ | [`namespace.py`](../../neuroswarm_arm/runtime/memory/namespace.py) |
| retention/ | [`ttl.py`](../../neuroswarm_arm/runtime/memory/ttl.py) + [`policies.py`](../../neuroswarm_arm/runtime/memory/policies.py) |
| summarization/ | [`summarizer.py`](../../neuroswarm_arm/runtime/memory/summarizer.py) |
| providers/ | [`providers/`](../../neuroswarm_arm/runtime/memory/providers/) — JSON emergency only |

Legacy path [`mem0/`](../../neuroswarm_arm/runtime/memory/mem0/) re-exports adapter SDK client + Mem0Provider bridge.
