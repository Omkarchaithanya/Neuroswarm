# ADR 0007: Encapsulate SGLang — Do Not Duplicate

## Status

Accepted

## Context

DIPA historically scaffolded batching, prefix cache, and PD routers that risked reinventing SGLang.

## Decision

DIPA **must not** reimplement:

- RadixAttention / HiCache page tables
- Sarathi-style chunked-prefill schedulers
- Mooncake / NIXL transfer engines
- SGLang continuous batcher or speculative kernels

DIPA **may**:

- Call SGLang HTTP / router / PD bootstrap APIs behind `SGLangBackend`
- Record NEXUS metrics and OTEL spans around those calls
- Orchestrate heterogeneous decode via `recompute` with explicit metrics
- Own agent policy (AQR/AWPP/MAKS/RTG/ArmCascade)

## Consequences

- Smaller, more correct DIPA surface
- Upstream SGLang improvements flow through without DIPA forks
- Clear ownership boundary for code review
