# Adaptive Context Runtime (Context OS)

ArmCascade **Layer 4** — Context Operating System for NEXUS-ARM.

**Not RAG. Not a vector DB.** Mem0 = cognitive memory runtime; OKF = knowledge OS. Merge only at assembly.

**Mission:** Request → smallest high-information context that still preserves every fact required for the task.

Compression is **measured** (`compression_ratio`, `information_retained`, `token_reduction`, latency) — no fixed percentage guarantee.

## Naming

| Name | Role |
|------|------|
| **ACR / Context OS** | This package (`neuroswarm_arm.runtime.acr`) |
| **AWPP** | Pre-warm predictor (peer); may consume ACR hints |
| **MAKS / KV** | Inference KV — orthogonal |

## Quick start

```python
from neuroswarm_arm.runtime.acr import build_acr

acr = build_acr(memory=neuro_memory, okf=okf_runtime)
snap = acr.build_context("NUMA-aware cascade policy", owner="alice", agent_role="architect")
print(snap.prompt)
print(snap.stats.compression.compression_ratio, snap.stats.compression.information_retained)
```

## Env

- `NSA_ACR_ENABLED` (default `1`)
- `NSA_ACR_TOKEN_BUDGET` (default `2000`)
- `NSA_ACR_CACHE`, `NSA_ACR_CACHE_TTL_S`, `NSA_ACR_CACHE_MAX`
- `NSA_ACR_PROGRESSIVE`, `NSA_ACR_PARALLEL_RETRIEVE`
- `NSA_ACR_MIN_IMPORTANCE`, `NSA_ACR_STABLE_PREFIX`

## Docs

- [architecture.md](architecture.md)
- [api.md](api.md)
- [developer.md](developer.md)
- [roadmap.md](roadmap.md)
- [benchmark.md](benchmark.md)
- ADRs under [adr/](adr/)
