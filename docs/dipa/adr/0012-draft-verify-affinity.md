# ADR 0012: Draft/Verify CPU Affinity Policy

## Status

Accepted

## Context

Speculative decoding runs a small draft model and a larger verifier. On Axion
(single UMA) and Apple Silicon (P/E cores), pinning draft to a small core
subset (or E-cores) and verify to the remainder is a free locality win.

## Decision

1. Extend `ArmPlacement` with `draft_affinity_tag` / `verify_affinity_tag`,
   Apple `detect_apple_silicon()` via `hw.perflevel{0,1}.logicalcpu`, and
   `pcore_count` / `ecore_count`.
2. `CpuAffinityRouter.recommend(phase, plan)` prefers `uma_draft` /
   `uma_verify_large` when `plan.speculation` and metadata speculation enabled.
3. `ExecutionContext` carries `affinity_draft` / `affinity_verify`;
   `CascadeExecutor.generate_tier` pins via `sched_setaffinity` (Linux) or
   mach `thread_policy_set` (Darwin) when `GenerateRequest.speculative`.
4. Compose / env: `NSA_DRAFT_CPUSET`, `NSA_VERIFY_CPUSET`,
   `NSA_APPLE_ECORE_FOR_DRAFT`, gated by `NSA_DRAFT_VERIFY_AFFINITY` and
   `strategies.draft_verify_affinity.enabled`.

## Consequences

- Draft/verify no longer fight for the same cores under speculation.
- Hosts without `sched_setaffinity` degrade gracefully (return False).
- Reversible: set `NSA_DRAFT_VERIFY_AFFINITY=0`.
