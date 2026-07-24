# Measured (Axion KleidiAI capture)

Sources: `docs/evidence/latest/run_all.json` (2026-07-18) + live layer verify 2026-07-21 (`docs/evidence/latest/layer-verify/` + [`LAYER_SCORECARD.md`](LAYER_SCORECARD.md)).

| Metric | Measured | Notes |
|---|---|---|
| Router top-1 accuracy | **100%** (2026-07-21 bench) / **83.3%** (2026-07-18 pack) | Live `work/benchmarks/router_accuracy.json`; 6-tool set. Pitch 40-tool/92% **not** measured. |
| Router avg token reduction | **15.7%** (2026-07-21) / **16.0%** (2026-07-18) | Schema Top-K vs full set |
| Tools-route prompt cut (sample) | **47%** | 600 → 318 tokens (2026-07-18 sample) |
| Tools indexed | **6** | web-search, github, browser, slack, postgres, s3 |
| Live chat tool Top-K | **3 schemas** | e.g. S3 + Postgres + GitHub on cascade chat |
| Cascade demo `tier_used` | **2–3** | 2026-07-21 chat used tier 3 |
| ASCR acceptance rate | **≈0.92–0.96** (logits smoke) / **~0.42** (older scrape) | Speculative logits path live; ordinary chat may still be `quality_cascade` |
| ASCR speculation gain | **≈0.33** (logits smoke) / **0** (quality-cascade chat) | Not a 2–4× throughput proof |
| Governor mean cap | **268** | vs legacy **666** (2026-07-18) |
| Economics savings score | **0.57** | `run_all` economics (2026-07-18) |
| Budget admit | **accept** | `budget_admit_total{result="accept"}` live; USD/tokens/latency dims present |
| GEPA e2e | **OK** | approve+deploy; `teacher=http` (2026-07-21) |
| AROP optimize | **often rejected** | statistical validation — honest non-promotion |
| Performix code_hotspots | **OK prior / unavailable this window** | Prior PID capture ~79% `libggml-cpu`; live refresh `source=unavailable` at verify time |
| Instruction Mix SIMD (Kleidi vs stock) | **Kleidi NEON 3.41% + SVE 0.94%** vs **stock NEON 2.14% + SVE 1.19%** | see `docs/evidence/performix/COMPARISON.md` |
| Obs scrape topology | **single gateway job** | Compose only |
| NUMA nodes | **1** | `locality_mode=cache_aware`; cpusets 0-1/2-4/5-7 |
| SGLang image | **arm64 in manifest** | PD profile not required for scorecard |
| Unit packs | **90 passed** | haoe + armcascade + router + dipa + evolution |
