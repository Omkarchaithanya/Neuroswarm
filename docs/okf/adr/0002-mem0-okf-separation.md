# ADR-0002: Mem0 and OKF never share storage

## Status

Accepted

## Decision

Mem0 / Cognitive Memory Runtime stores conversation-derived facts. OKF stores institutional documents. Merge happens only at prompt assembly time.

## Clarification (2026-07)

Episodic memory is accessed through `neuroswarm_arm.runtime.memory.NeuroMemory`
and `Mem0Adapter`. Mem0 OSS is the primary memory engine (official SDK).
JSON store is emergency circuit-breaker only. This ADR still forbids sharing
storage with OKF.
