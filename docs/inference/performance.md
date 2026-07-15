# Performance Guide

## Thread count

Set `-t` to vCPU count for the tier (compose: `TIER*_THREADS`). Under-threading leaves Arm cores idle.

## KleidiAI

Build with `-DGGML_CPU_KLEIDIAI=ON -DGGML_NATIVE=ON`. Verify:

```text
load_tensors: CPU_KLEIDIAI model buffer size = ...
```

## Cascade / ASCR

**ASCR** (Adaptive Speculative Cascade Runtime) selects proposal strategy, draft length, verification mode, acceptance policy, and escalation graph dynamically.

Working paths: draft-model (Tier1) + block verify (Tier2); self-spec / n-gram; quality-cascade fallback when logits unavailable. Prefer server-side draft/`--spec-self` when available.

See [`docs/armcascade/Architecture.md`](../armcascade/Architecture.md).

## Batching

llama-server continuous batching/slots exposed via capabilities + `SlotClient`. Prefer server slots over reinventing GGML scheduler.
