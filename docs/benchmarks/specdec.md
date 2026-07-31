# SpecDec SpecBench-style benchmark

Gap G16 baseline suite. Same workloads for every speculative-decoding Gap.

## Run

```bash
# mock (CI / default)
NSA_SPECDEC_BENCH=1 uv run python benchmarks/specdec_bench.py \
  --out work/benchmarks/specdec_bench.json

# Makefile
make bench-spec
make bench-spec-live   # real tier backends
```

Gate: `NSA_SPECDEC_BENCH=1` **or** `strategies.specdec_bench.enabled: true`.
Safe default is off in [`strategies.yaml`](../../neuroswarm_arm/runtime/armcascade/config/strategies.yaml).

## Workloads

Defined in [`benchmarks/specdec_workloads.yaml`](../../benchmarks/specdec_workloads.yaml):

| name | intent |
|------|--------|
| `chat_short` | short Q&A |
| `code_completion` | partial code prompts |
| `rag_long` | `[LONG_DOC_4K]` expanded to ~4k deterministic tokens |
| `tool_use` | JSON tool-call prefix |
| `reasoning` | short math |

`iterations_per_prompt: 4` by default.

## Verify strategies

Cycles `block`, `logits`, `tree` when each is enabled in `strategies.yaml`
(and not disabled via `NSA_ASCR_LOGITS_ENABLED` / `NSA_ASCR_TREE_ENABLED`).
Sets `NSA_ASCR_DEFAULT_VERIFIER` per cycle and rebuilds `build_dipa`.

## Metrics (JSON)

Top-level + `overall` / `by_verify` / `by_workload`:

| key | meaning |
|-----|---------|
| `tokens_per_sec` | effective completion tokens / wall seconds |
| `acceptance_rate` | accepted / draft tokens |
| `mean_accepted_prefix_len` | mean accepted prefix length |
| `p50_ttft_ms` / `p95_ttft_ms` | TTFT percentiles |
| `mean_draft_ms` / `mean_verify_ms` | engine timers if present; else 40/60 split of cascade latency |
| `ascr_speculation_gain` | **SpecBench proxy** = accepted/draft (mock-safe, always finite) |
| `engine_ascr_speculation_gain` | honest engine metric (0 under `text_agree` / `quality_cascade`) |

Exit code is always `0` (benchmark, not a gate). CI comments on PR if SpecBench
gain drops **>5%** vs [`17-spec-bench-baseline.json`](../evidence/latest/layer-verify/17-spec-bench-baseline.json).

## Streaming

Requests use `stream=True` (streaming-first). Non-stream is not the primary path.

## Reading results

1. Prefer `overall.ascr_speculation_gain` for Gap vs Gap comparison.
2. Check `engine_ascr_speculation_gain` for lossless honesty (live logits path).
3. Slice `by_verify` / `by_workload` for regressions in one strategy or prompt class.
