# Gap Analysis: NEXUS-ARM DIPA vs Upstream SGLang

## Scope

Authoritative NEXUS sources: `docs/dipa/*`, ADRs `0001–0005`, `docs/inference/*`, `docs/maks/axion-compatibility.md`.  
Vision docs (`00–07`, hackathon) are **not** Axion truth.

Upstream SGLang capabilities studied: RadixAttention, HiCache, continuous batching, chunked prefill, PD disaggregation (Mooncake/NIXL), router, OpenAI APIs, health/metrics, OpenTelemetry, speculative decoding, Arm64 CPU engine (`SGLANG_USE_CPU_ENGINE=1`).

## Capability matrix

| Capability | SGLang upstream | NEXUS (pre-redesign) | Decision |
|------------|-----------------|----------------------|----------|
| RadixAttention / prefix cache | Native radix tree + HiCache | MAKS + `PrefixCacheEngine` metadata only | **Encapsulate** via `PrefixCacheManager` → SGLang; bridge hit stats to MAKS/AWPP |
| Continuous batching | Native scheduler | `ContinuousBatcher` unused; llama slots only | Abstract in `BatchScheduler`; enable when caps allow |
| Chunked prefill | Native (`chunked-prefill-size`) | Missing | `ChunkPlanner`/`ChunkExecutor` call SGLang; **do not** reimplement Sarathi |
| PD disaggregation | Mooncake / NIXL + router | Interfaces + dead routers | Wire `PrefillManager`/`DecodeManager`; native mode pass-through |
| Speculative decoding | Native | ArmCascade + self-speculation | Keep ArmCascade; optional SGLang draft behind HAL |
| Streaming | SSE / OpenAI stream | Backend SSE exists; ARMORA word-split fake | True `decode()` async iterator |
| Health / metrics / OTEL | Built-in | DIPA collectors + stubs | Compose backend + DIPA spans |
| OpenAI-compatible API | Yes | llama-server + gateway | `SGLangBackend` HTTP client |
| Worker lifecycle | `launch_server` | llama `ProcessSupervisor` only | SGLang supervisor + compose profile |
| Router | `sglang_router` PD LB | DIPA `DecisionEngine` | DIPA owns agent policy; optional SGLang router URL for prefill pool |
| NUMA / Arm | CPU thread bind | Best-effort affinity | Keep hooks; Axion single-socket fallback |
| Cross-engine KV (SGLang → llama.cpp) | N/A (same-engine PD) | Not possible as binary handoff | **`recompute` mode** (honest); `native_sglang` when same-engine |

## Hard constraint

SGLang paged KV layout ≠ llama.cpp GGML KV. Binary heterogeneous transfer is **not** production-ready upstream. DIPA therefore supports:

1. `native_sglang` — same-engine PD (Mooncake/NIXL pass-through)
2. `recompute` — Axion default for SGLang prefill + llama.cpp decode
3. `unavailable` — RDMA/Mooncake reported `UNAVAILABLE` on Axion (ADR-0005)

## What DIPA must never duplicate

- Radix tree / HiCache page table
- Chunked-prefill token-budget scheduler internals
- Mooncake / NIXL transfer engines
- SGLang continuous batcher / speculative kernels

## What DIPA owns

- Agent-aware planning (AQR/AWPP/MAKS/RTG connectors)
- ArmCascade quality tiers on decode path
- PD orchestration abstractions and transfer-mode honesty
- NEXUS metrics / health / OTEL envelopes
- Stable HAL so upper layers never import `sglang`
