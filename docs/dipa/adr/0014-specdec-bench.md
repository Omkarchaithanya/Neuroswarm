# ADR 0014: SpecDec SpecBench Baseline Suite

## Status

Accepted

## Context

Each speculative-decoding Gap (logits, tree, affinity, EAGLE-3, …) needs a
shared, CI-runnable measurement surface. Ad-hoc probes
(`scripts/probe-ascr-speculation.py`) and the ASCR smoke bench are useful but
not workload-normalized across Gaps.

## Decision

1. Add `benchmarks/specdec_workloads.yaml` + `benchmarks/specdec_bench.py`
   (SpecBench-style): chat / code / RAG / tool / reasoning; cycle enabled
   verify strategies `block` / `logits` / `tree`.
2. Gate with `NSA_SPECDEC_BENCH` (safe default off) and reversible
   `strategies.specdec_bench.enabled` in `strategies.yaml`.
3. Report SpecBench `ascr_speculation_gain = accepted/draft` for mock-CI
   stability, plus `engine_ascr_speculation_gain` for LOSSLESS honesty
   (engine still reports 0 under text-agree / quality-cascade).
4. CI job `spec-bench` on PR + nightly; artifact JSON; soft PR comment on
   >5% SpecBench gain drop vs `docs/evidence/latest/layer-verify/17-spec-bench-baseline.json`.
5. No new heavy deps; mock path uses existing `build_dipa(use_mock=True)`.

## Consequences

- Every Gap can land evidence against the same baseline JSON.
- Live Axion numbers stay Makefile-local (`bench-spec-live`).
- Reversible: unset `NSA_SPECDEC_BENCH` and keep `specdec_bench.enabled: false`.
