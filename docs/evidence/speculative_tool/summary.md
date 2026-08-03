# Speculative tool calling — evidence

status: captured  
generated: 2026-08-03T14:10:07Z  
host: `Windows-11-10.0.26200-SP0`  
mode: `inproc`  

Judges: read this in ~60 seconds.

## Architecture

```text
  draft predictor ----+
                      +--> SpeculativeExecutor --> ToolOutputCache / MCP
  cascade generate ---+         |
                                v
                      match tool_call key -> speculative_hit + time_saved
```

- Baseline: `NSA_TOOL_SPEC_ENABLED=0` — cascade then sync MCP (no overlap).
- Speculative: `NSA_TOOL_SPEC_ENABLED=1` — predict || cascade; warm half prompts first.
- Prompts: `benchmarks/test-data/tool_prompts.jsonl` (10 calculator / 10 echo / 10 search).

## Measured summary

| metric | value |
|---|---:|
| hit_rate | **0.5** |
| avg_time_saved_ms | **46.801** |
| p50 time_saved_ms | **57.947** |
| p95 time_saved_ms | **75.902** |
| tokens_per_dollar_delta | **5722.91** |
| mean latency baseline_ms | 149.678 |
| mean latency speculative_ms | 102.877 |
| predicted_correct_rate | 0.5 |
| latency_speedup | 1.4549 |

Warm prompts: **15** / 30.

## Artifacts

| file | what |
|---|---|
| `speculative_tool_bench.json` | full jq-able result + per-prompt rows |
| `speculative_tool_bench.csv` | flat table for spreadsheets |
| `hit_rate.png` | cache-hit vs miss counts |
| `latency_cdf.png` | CDF of time_saved_ms |

## Reproduce

```bash
make bench-tool-spec
# or:
uv run python benchmarks/speculative_tool_bench.py \
  --out benchmarks/results/speculative_tool_bench.json
uv run --group bench python scripts/render_speculative_tool_evidence.py
```

## Honesty

- Default mode is **inproc** (real `SpeculativeEngine` + timed FakeMCP).
- Cascade/MCP delays configurable via `NSA_TOOL_SPEC_BENCH_CASCADE_S` / `_MCP_S`.
- `tokens_per_dollar_delta` = ref_tpd * (baseline_ms/spec_ms - 1); ref from `NSA_TOOL_SPEC_REF_TPD` (default 12580).
- Live gateway: add `--live` (needs stack up; slower than 5 min budget if LLM cold).
