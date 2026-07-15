# ADR 0002: Backend Plugin HAL

## Status

Accepted

## Context

Multiple inference runtimes (llama.cpp today; vLLM / ExecuTorch / LiteRT tomorrow) must plug in without rewriting the planner.

## Decision

All runtimes implement `InferenceBackend` and register in `BackendRegistry`. Capabilities are declarative (`BackendCapabilities`).

## Consequences

- New backends = adapter + register
- Kernel / planner / cascade depend only on the ABC
