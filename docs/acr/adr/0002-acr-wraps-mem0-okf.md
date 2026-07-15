# ADR-0002: ACR wraps Mem0 and OKF behind ports

## Status

Accepted

## Decision

ACR adapters call `NeuroMemory` and `OKFNexusRuntime`. Storage never merges. Assembly is the only merge point (replaces raw `merge_mem0_okf` when `NSA_ACR_ENABLED=1`).

## Consequences

Both backends remain independently replaceable via DI.
