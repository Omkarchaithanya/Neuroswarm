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
| Economics savings score | **0.57** | `run_all` economics |
| Performix code_hotspots | **OK** | `source=apx`, 25 hotspots in snapshot |
| Instruction Mix SIMD share (Kleidi vs stock) | **Kleidi NEON 3.41% + SVE 0.94%** vs **stock NEON 2.14% + SVE 1.19%** | from `03-instruction_mix_dynamic_kleidi.json` / `04-…baseline.json` (live decode load; see `COMPARISON.md`). Legacy static `02`/`static_instruction_mix.csv` (1.61%/0.34%) is superseded. |
| NUMA nodes | **1** | Option A — C4A single UMA; `locality_mode=cache_aware` (cpuset 0-1/2-4/5-7); `cross_numa_penalty_applicable=false` |
| SGLang image | **arm64 in manifest** | `lmsysorg/sglang:latest` verified |
