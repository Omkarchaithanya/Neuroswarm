# ADR 0005: Axion Software Fallbacks

## Status

Accepted

## Context

Primary deploy target is GCP Axion `c4a-standard-8`: homogeneous CPUs, no exposed MTE/CXL, weak/absent NUMA guarantees. Windows dev hosts lack `sched_setaffinity`.

## Decision

- Affinity: best-effort; `NoOpAffinityProvider` when bind fails
- NUMA: single-node placement via `NumaAdapter`
- MTE/CXL: provider stubs returning empty/unavailable
- networkx optional: pure-Python DAG fallback for minimal images
- Never raise because a hardware feature is missing

## Consequences

- Production-correct behavior on Axion today
- Feature detector still surfaces SVE2/etc. when present for future paths
- Docs must not claim hardware acceleration that is not active
