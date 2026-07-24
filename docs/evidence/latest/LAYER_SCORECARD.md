# Layer live verification scorecard (Axion)

**When:** 2026-07-21T10:29–10:36Z UTC  
**Host:** neuroswarm-axion Compose-only (`k3s` inactive, NodePort 30080 down)  
**Base URL:** `http://127.0.0.1` (nginx → gateway)  
**Unit packs (local):** `90 passed` (`tests/runtime/{haoe,armcascade,router,dipa}` + `tests/evolution`)  
**Artifacts:** [`docs/evidence/latest/layer-verify/`](layer-verify/) · driver [`scripts/layer-live-verify.sh`](../../../scripts/layer-live-verify.sh)

Verdict key: **PASS** = live IO matches honest architecture · **PARTIAL** = works but pitch overstated / fallback · **FAIL** = broken smoke · **Marketing-only** = no implementation for the pitch wording

---

## Scorecard vs pitch

| Pitch claim | Verdict | Live evidence |
|---|---|---|
| **HAOE** — SVE2 task scheduler, 60–80% latency cut | **PARTIAL** (kernel) + **Marketing-only** (SVE2/60–80%) | Chat `planner_id=haoe.chat`; metrics `haoe_workflows_total`, `haoe_workflow_latency_ms≈20.7s`. `/health` has no `haoe` blob. **No** `nexus_hw_sve2_utilization`. `json_sve2.c` remains stub. |
| **AQR** — per-role quant + codebook in vector registers | **PARTIAL** (policy) + **Marketing-only** (codebook) | `pick_quant_primary`: reasoning=`Q4_K_M`, others=`Q4_0`; chat `quant_policy=Q4_0`. Package codebook mentions = **0**. |
| **ARM-Native Inference** — NUMA + Kleidi + llama/SGLang | **PASS** (Kleidi+cascade) · **PARTIAL** (NUMA/SGLang) | Tiers = `nexus-arm/llama-kleidiai:server`. Chat OK, `tier_used=3`. NUMA nodes=**1**, `locality_mode=cache_aware` (not NUMA-split). SGLang: **arm64 in manifest** PASS; PD off (`pd_enabled=0`). |
| **Speculative Cascade (ASCR)** — 3-tier, 2–4× | **PARTIAL** | Live logits smoke: `accept_mode=speculative_logits`, modes=`speculative`×3, `ascr_acceptance_rate≈0.92–0.96`, `ascr_speculation_gain≈0.33`. Ordinary chat still often `ascr_mode=quality_cascade` with `logits_available=0` / gain 0. **Not** proven 2–4× throughput. |
| **Cost-Aware Orchestrator** — xRouter RL + GEPA + budget + MCP | **PARTIAL** + **Marketing-only** (xRouter RL) | Budget dims live (`budget_remaining{cost_usd,tokens,latency_ms,…}`, `budget_admit_total`). `/v1/cost/economics` returns costs. GEPA e2e: **approve+deploy OK**, `teacher=http`. AROP `/arop/optimize` often **rejected** by statistical validation (honest). **No** `xRouter` module / PPO. |
| **Self-Optimizing Loop** — Performix → GEPA → thresholds | **PARTIAL** | GEPA text path works. Performix snapshot at verify time: `source=unavailable` (`apx_recipe_failed`) — honest empty; prior PID capture still on metrics (`libggml-cpu` ~79%). GEPA does **not** own ASCR thresholds (ADR). |
| **Semantic MCP Router** — BGE+FAISS, 40→3, 92% cut | **PARTIAL** | Live chat selected **3** schemas (`S3`,`Postgres`,`GitHub`). Index size **6**. Bench: top-1/3/5 = **100%**, `avg_token_reduction=15.69%`, `ann_backend=exact` (gateway runtime uses turbovec). MCP templates **PASS (6)**. Pitch **40 tools / 92%** not measured. |

---

## Per-layer detail

### 1. HAOE
- **Working:** orchestration planner on chat path; workflow counters increment.
- **Not working as pitched:** SVE2 JSON scheduler / 60–80% latency reduction — not measured; no SVE util metric.
- Cite: `01-health-summary.json`, `03-metrics-filtered.txt`, `02-chat.json` (`planner_id`).

### 2. AQR
- **Working:** role→GGUF string policy used on live chat.
- **Not working as pitched:** codebook in Neon/SVE registers.
- Cite: `04-aqr.json`, chat `metrics.quant_policy`.

### 3. ARM-Native Inference
- **Working:** KleidiAI llama.cpp 3-tier cascade produces coherent completions.
- **Honest NUMA:** single UMA + cache-aware cpusets (`0-1` / `2-4` / `5-7`).
- **SGLang:** image multi-arch OK; soft/native PD not exercised this run.
- Cite: `13-kleidi.txt`, `02-chat-summary.json`, `01-health-summary.json`, `11-sglang.txt`.

### 4. Speculative Cascade / ASCR
- **Working:** 3-tier path; logits smoke reaches speculative accept with non-zero gain.
- **Fallback still real:** quality_cascade on short chat without logits.
- Cite: `05-ascr-smoke.txt`, `12-product-gaps.txt`, chat `metrics.ascr_mode`.

### 5. Cost / GEPA / “xRouter”
- **Working:** ARMORA budget gauges, RCIS economics, GEPA text approve/deploy with HTTP teacher.
- **Not working as pitched:** xRouter RL / PPO closed loop.
- Cite: `08-economics.json`, `09-gepa-e2e.txt`, `09-arop-optimize.json`.

### 6. Performix → GEPA → thresholds
- **Working:** GEPA independent of threshold knobs; prior Performix hotspots still scraped.
- **Gap:** live refresh failed this window; ASCR not bound to AROP policy registry for auto threshold drift.
- Cite: `10-performix.json`, `09-gepa-e2e.txt`.

### 7. Semantic MCP tool router
- **Working:** Top-K tool schemas on live chat; accuracy bench 100% on 6-tool set; ~16% avg token reduction.
- **Not working as pitched:** 40→3 / 92% context cut.
- Cite: `06-router_accuracy.json`, `07-mcp-templates.txt`, chat `tool_schemas_used`.

---

## Smoke blockers fixed this pass

1. [`scripts/layer-live-verify.sh`](../../../scripts/layer-live-verify.sh) — router bench via `uv run` / `.venv` (system `python3` lacked pydantic).
2. Synced missing [`scripts/verify-mcp-templates.sh`](../../../scripts/verify-mcp-templates.sh) to Axion; MCP templates re-smoke **PASS**.

---

## Deploy honesty

- Compose gateway + Kleidi tiers + proxy + OTEL + qdrant up.
- `k3s` **inactive**; dual-stack contention from prior incident remains cleared for this scorecard.

## What judges should hear

Ship **working** Kleidi cascade, ASCR (with honest speculative vs quality modes), AQR policy strings, semantic Top-K router (6 tools), ARMORA budgets, GEPA text evolution, and HAOE as a Python planner/kernel. Do **not** claim SVE2 HAOE scheduling, AQR vector-register codebooks, xRouter RL, 40-tool/92% routing, or unconditional 2–4× speculative throughput.
