# ADR 0003: Immutable versioned policies

## Status

Accepted

## Context

In-place config edits prevent rollback and lineage.

## Decision

All optimizations produce frozen `RuntimePolicy` objects with `content_hash`, parent/rollback ids, and registry slots (active/canary/shadow).

## Consequences

- PolicyRegistry persistence under `work/arop/policy_registry.json`.
- OKF stores engineering copies; Mem0 stores runtime evolution memory (ADR-0002 Mem0≠OKF).
