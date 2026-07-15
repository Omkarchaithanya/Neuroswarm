# ADR 0002: Provider Hardware Abstraction Layer

## Status

Accepted

## Context

GCP Axion does not expose MTE, CXL, or reliable user-space NUMA. Blueprint docs assume Graviton5-class topology. Hardcoding either platform breaks portability.

## Decision

All hardware capabilities go through providers (`CPU`, `Topology`, `Affinity`, `Memory`, `KV`, `Scheduling`). Missing features report `UNAVAILABLE` and use software fallbacks. Future NUMA/MTE/CXL/hwloc/SME plug in behind the same interfaces.

## Consequences

- Scheduler and workflow code never import sysfs/NUMA details directly
- Axion demos remain honest (no fake CXL claims)
- Future Neoverse boxes adopt acceleration without redesign
