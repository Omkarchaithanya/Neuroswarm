# ASCR Benchmark Guide

## Metrics

| Metric | Meaning |
|--------|---------|
| `ascr_acceptance_rate` | Accepted / (accepted+rejected) tokens |
| `ascr_rejection_rate` | Rejected fraction |
| `ascr_draft_tps` / `ascr_effective_tps` | Draft vs accepted throughput |
| `ascr_speculation_gain` | Accepted fraction of draft (proxy for speedup) |
| `ascr_saved_forward_passes` | Estimated target forwards saved |
| `ascr_quality_cascade_total` | Requests in non-speculative quality mode |
| `dipa_cascade_hit_rate` | Alias: tier-1 finish fraction |

**Do not** treat quality-cascade hit rate as speculative speedup.

## Runner

```bash
python benchmarks/ascr_benchmark.py
# → work/benchmarks/ascr_benchmark.json
```

Also: legacy `benchmarks/cascade_acceptance.py`.

## Methodology (SpecBench-inspired)

1. Warm backends / KleidiAI ready.
2. Fixed prompt suite (factual, code, long repetitive, reasoning).
3. Record TTFT, tok/s, accept length, rejected tokens, CPU, NUMA locality.
4. Report speculation gain separately from quality-cascade routing gain.
5. Gate: accept ≥70% on factual/chat before claiming 1.5–2.3×.
