# ADR 0001: AROP is Plane 5, not MAKS

## Status

Accepted

## Context

Hackathon and MAKS docs define **NEXUS Layer 5 = MAKS**. Vision docs call the Performix→GEPA loop **Plane 5 Evolution**.

## Decision

Implement the Autonomic Runtime Optimization Plane as **Plane 5 / AROP** under `neuroswarm_arm/evolution/`. Keep MAKS as Layer 5.

## Consequences

- Docs must disambiguate Layer 5 vs Plane 5.
- AROP may optimize MAKS knobs via adapters; it does not own KV lifecycle.
