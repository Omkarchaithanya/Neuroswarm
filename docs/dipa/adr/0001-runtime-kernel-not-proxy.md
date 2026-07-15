# ADR 0001: Inference Runtime Kernel, Not a Proxy

## Status

Accepted

## Context

Docs sometimes call DIPA a “proxy.” A reverse proxy / API gateway cannot own cascade, quant routing, prefill/decode pools, or backend plugins.

## Decision

DIPA is the **Inference Runtime Kernel** (Layer 2). HTTP routing is incidental. Every inference decision flows through DIPA.

## Consequences

- Agents never call llama.cpp / vLLM / ExecuTorch / LiteRT directly
- HAOE coordinates; DIPA executes inference
- Surface area larger than a stub router — intentional
