# ADR 0008: ASCR Replaces Heuristic Cascade

## Status

Accepted

## Context

DIPA `cascade/` implemented sequential full-generation quality escalation with a heuristic text confidence scorer. Vision docs called this the “Speculative Cascade Router.” Self-speculation drafts were computed but never wired into verification. That design cannot deliver speculative throughput gains and cannot extend to EAGLE/Medusa/PARD without redesign.

## Decision

1. Introduce **Adaptive Speculative Cascade Runtime (ASCR)** as package `neuroswarm_arm.runtime.armcascade`.
2. ASCR implements `ICascadeEngine` and is constructed by `build_dipa()` via `build_ascr()`.
3. Rename product concept **Speculative Cascade Router → Adaptive Speculative Cascade Runtime (ASCR)**. ArmCascade remains the family name.
4. DIPA remains Layer 2 Inference Runtime Kernel (ADR-0001). ASCR is the throughput optimization subsystem.
5. `dipa/cascade/` becomes a compatibility shim re-exporting ASCR types for one release.
6. New speculative algorithms require one strategy class + registry + YAML — no engine redesign.
7. Do not duplicate SGLang speculative kernels (ADR-0007). Optional SGLang draft stays behind HAL.

## Consequences

- Real propose → verify → accept → escalate → adapt loop
- Adaptive thresholds and escalation DAGs
- Plugin surface for future EAGLE/Medusa/PARD
- Metrics: `ascr_*` plus `dipa_cascade_*` aliases
- Honest quality-cascade fallback when logits unavailable
