# ADR 0002: Reflection proposes only

## Status

Accepted

## Context

Direct GEPA/Performix → runtime mutation is unsafe and unreproducible.

## Decision

`ReflectionStrategy` (including GEPA) may only emit `PolicyDelta`. Runtime changes require Optimization → Experiment → Validation → Safety → Deployment.

## Consequences

- GEPA never imports ASCR/HAOE mutators.
- Human / rule / hybrid strategies share the same port.
