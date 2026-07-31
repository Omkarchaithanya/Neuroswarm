# AROP v1 — rule-based Performix-driven cascade tuner

Standalone CLI tuner. **Not** GEPA / Mem0 / PPO / `RuntimeOptimizer`.

## Honesty

- Parses real `apx` JSON only (`source=apx`). Demo/synthetic → fail loud.
- Missing/null required fields → `AropMetricMissing` (never default to `0`).
- No runtime GGUF weight swap. Axion tiers are already `Q4_0`.
- `draft_len` / `accept_threshold` are **gateway-side** (`NSA_ASCR_*`); live apply restarts `gateway` only.
- Never names instruction-mix shares as `simd_util`.

## Quick start

```bash
# Preflight (Axion)
NSA_PERFORMIX_ALLOW_DEMO=0 bash scripts/arop-preflight.sh path/to/code_hotspots.json

# Dry-run (default)
python -m neuroswarm_arm.arop.evolve_cycle \
  --hotspots path/to/code_hotspots.json \
  --acceptance benchmarks/results/acceptance_rate_live.json \
  --governor benchmarks/results/governor_live.json \
  --instruction-mix path/to/instruction_mix.json \
  --tier-metrics-url http://127.0.0.1:8081

# Live apply (explicit)
python -m neuroswarm_arm.arop.evolve_cycle --apply ...
```

## Rules

| Rule | Trigger | Action |
|------|---------|--------|
| R0 | `Unknown symbol @ 0x` >20% or top=`posix_fallocate`/mmap | skip cycle |
| R1 | top hotspot contains `ggml` & pct>60 and tier1_hit_rate<0.6 | draft_k -= 1 (floor 2) |
| R2 | tier1_hit_rate>0.9 and latency slack | draft_k += 1 (ceiling 8) |
| R3 | thinking_tokens_avg > cap×1.15 | tighten governor_thinking_cap 10% (floor 256) |

One parameter change per cycle. Rollback if tok/s or tier1 hit-rate regresses >5%.
