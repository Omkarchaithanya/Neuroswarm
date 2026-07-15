# ADR 0006: SGLang Prefill + llama.cpp Decode

## Status

Accepted

## Context

NEXUS needs modern PD-aware serving on GCP Axion (CPU-first, KleidiAI decode) without coupling HAOE/ARMORA to engine internals. SGLang provides RadixAttention, chunked prefill, and continuous batching. llama.cpp provides Axion-optimized decode.

SGLang KV pages are not binary-compatible with llama.cpp GGML KV.

## Decision

1. Prefer **SGLang** as dedicated **prefill** runtime when `NSA_DIPA_PD_MODE` is `soft` or `native`.
2. Prefer **llama.cpp** as dedicated **decode** runtime on Axion.
3. KV transfer modes:
   - `native_sglang` — same-engine PD via SGLang router / Mooncake / NIXL (pass-through only)
   - `recompute` — default for heterogeneous SGLang→llama.cpp (measure recomputed tokens)
   - `unavailable` — RDMA engines not present on Axion
4. Fused `generate()` remains default when `PD_MODE=off` or prefill backend unhealthy.
5. ArmCascade continues to own multi-tier **quality** on the decode path.

## Consequences

- Upper layers stay engine-agnostic
- Axion demos remain honest (no fake binary KV transfer)
- Prefill wins from shared agent prefixes via encapsulated RadixAttention
