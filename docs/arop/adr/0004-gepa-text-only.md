# ADR 0004: GEPA optimizes text only

## Status

Accepted

## Context

Official GEPA (Genetic-Pareto) evolves textual components via ASI, reflective mutation, merge, and Pareto selection. An earlier NEXUS stub labeled rule-based numeric knob deltas as “GEPA”, violating the official philosophy.

## Decision

1. GEPA lives under `evolution/reflection/gepa/` as an AROP Plane 5 Reflection subsystem.
2. Candidates are `dict[str, str]` only (prompts, OKF policies, tool descriptions).
3. Hardware and cascade numeric knobs are **non-GEPA** (`RuleBasedReflectionStrategy`).
4. Deployment of GEPA text requires `ApprovalGate` — no auto-promote.
5. Performix remains an ObservationProvider / ASI source only.
6. Optional soft import of the `gepa` package; CI uses the local faithful loop.

## Consequences

- `GEPAReflectionStrategy.propose()` returns no `PolicyDelta` knobs.
- Hybrid mode runs GEPA text evolution + RuleBased knobs separately.
- ArmCascade/ASCR is not redesigned.
