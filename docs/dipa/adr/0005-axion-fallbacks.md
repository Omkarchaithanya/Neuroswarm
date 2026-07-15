# ADR 0005: Axion Software Fallbacks

## Status

Accepted

## Context

GCP Axion MVP: homogeneous CPUs, weak/absent user-space NUMA, no MTE/CXL guarantees.

## Decision

- Prefill/decode pools are software partitions from config cores
- Affinity best-effort; no-op on Windows / restricted hosts
- NUMA reports single node 0
- Never raise because hardware acceleration is missing
- Do not claim KleidiAI / MTE / CXL wins unless feature detector says AVAILABLE

## Consequences

- Honest Axion demos
- Neoverse / Graviton / Cobalt adopt acceleration behind same interfaces
