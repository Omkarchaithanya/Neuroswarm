# Measured (Axion KleidiAI capture)

Source: `docs/evidence/latest/run_all.json` + Prometheus + chat + Performix (2026-07-18).

| Metric | Measured | Notes |
|---|---|---|
| Router top-1 accuracy | **83.3%** | top-3/top-5 = 100% |
| Router avg token reduction | **16.0%** | schema Top-K vs full set |
| Tools-route prompt cut (sample) | **47%** | 600 → 318 tokens |
| Tools indexed | **6** | web-search, github, browser, slack, postgres, s3 |
| Cascade demo `tier_used` | **2–3** | chat used tier 3 |
| ASCR acceptance rate | **~0.42** | Prometheus gauge |
| Governor mean cap | **268** | vs legacy **666** |
| Governor token reduction (stub GSM8K/HumanEval) | **~54%** | `benchmarks/governor_accuracy.py` |
| Economics savings score | **0.57** | `run_all` economics |
| Performix code_hotspots | **OK** | `source=apx`, 25 hotspots in snapshot |
| Instruction Mix SIMD share (approx) | **NEON 1.61% + SVE 0.34%** | from `static_instruction_mix.csv` |
| NUMA nodes | **1** | Option A — no NUMA-split claim |
| SGLang image | **arm64 in manifest** | `lmsysorg/sglang:latest` verified |
| MAKS multi-agent dedup savings | **87.5%** | 8 agents × 20 prompts; `layer-verify/14-maks-dedup.json` |
| MAKS sharing savings | **100%** | shared_pages/pages on dedup run |
| MAKS concurrent agents @ RAM budget | **127981** | `ram_budget / avg_kv_size` from dedup run |
