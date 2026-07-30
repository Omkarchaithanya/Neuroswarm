# Hardware claim mismatch report (Phase B)

**Status:** report only — **do not edit pitch/root docs until confirmed**.  
**Demo host reality:** GCP Axion `c4a-standard-8`, 8 vCPU, 1 NUMA, no MTE, no native CXL.  
**Generated:** 2026-07-30 (Performix live-telemetry fix track).

## Replacement target (canonical)

| Field | Honest value |
|-------|----------------|
| Demo host | GCP Axion `c4a-standard-8` (Neoverse-V2) |
| Cores / NUMA | 8 vCPU, **1 NUMA node** |
| MTE | Unavailable on this GCP guest — stubs raise / degrade |
| CXL | No native CXL memory pool on this VM — NVMe/mmap path |
| Grafana | On **`neuroswarm-obs`**, not Axion `:3000` |
| Performix UI path | Prometheus `nexus_performix_*` → Grafana (SSH tunnel `13000→3000` to obs) |

**Keep** (evidence-backed where cited in `docs/evidence/` / benchmarks): cascade ~95.2%, governor ~56.1%, KleidiAI +64%/+26%/+34%, KV tests, router measured reductions in `05-BENCHMARK-PLAN.md`.

---

## Scan results by file

### Root / pitch docs (plan scan targets)

| File | Claim / phrasing | Severity | Suggested replacement |
|------|------------------|----------|------------------------|
| [`00-EXECUTIVE-SUMMARY.md`](../../00-EXECUTIVE-SUMMARY.md) | Mostly Option A / Axion-correct. Mentions “hardware-adaptive NUMA/CXL/MTE that activates only when the host exposes it” and optional Graviton4/5 scale-up. | Low (OK if read carefully) | Keep; optionally add explicit “**not** shipping MTE/CXL on Axion demo”. |
| [`01-PROBLEM-STATEMENT.md`](../../01-PROBLEM-STATEMENT.md) | Already warns against “2-NUMA Graviton5 as the demo box”. Hardware honesty callout is Axion-first. | Low | Keep; no fantasy-as-demo. |
| [`02-ARCHITECTURE.md`](../../02-ARCHITECTURE.md) | Demo = Axion; CXL/MTE “activate only when topology HAL says”. | Low | Keep. |
| [`03-TECH-STACK.md`](../../03-TECH-STACK.md) | Primary = Axion; “Future \| Arm AGI CPU / native CXL”. Checklist: not Graviton5-as-demo. | Low | Keep “Future” row; ensure pitch decks don’t promote Future as current. |
| [`05-BENCHMARK-PLAN.md`](../../05-BENCHMARK-PLAN.md) | Axion affinity table (CPU 0–1 / 2–7). Aspirational column separate from Measured. | Low | Keep measured column; do not copy aspirational into Devpost without artifacts. |
| [`06-SUBMISSION-STRATEGY.md`](../../06-SUBMISSION-STRATEGY.md) | Anti-pattern table already rejects “NUMA-split Graviton5” as demo. | Low | Keep. |

**Verdict on plan scan targets:** residual fantasy-as-demo is largely already scrubbed. Remaining risk is **capability language** (CXL/MTE/NUMA-split) that a rushed judge may hear as “on this box.” Optional soft edit: one bold line on each pitch surface — “Axion demo: 1 NUMA, no MTE, no CXL.”

### Higher-risk residual files (fantasy phrasing still present)

| File | Claim | Severity | Suggested replacement |
|------|-------|----------|------------------------|
| [`hackathon_problem_statement.md`](../../hackathon_problem_statement.md) | Layer 5 “Uses ARM MTE for secure zero-copy…”; scoring rubric lists MTE + CXL as demonstrated; Pillar 3 “CXL 3.0 memory pool”. Axion honesty paragraph exists for NUMA but MTE/CXL still read as product facts. | **High** | Frame MTE/CXL as **architecture / future backends**; Axion path = NVMe/mmap + sharing stubs that raise when unavailable. |
| [`plan (1).md`](../../plan%20(1).md) | Graviton4/5 targets; “CXL 3.0 memory pool (sub-µs…)”; “MTE for zero-copy”; “2x concurrent agents”; “RDMA over Graviton4 as demo path”. | **High** | Relabel as vision/backlog; demo host = Axion Option A. |
| [`04-IMPLEMENTATION-PLAN.md`](../../04-IMPLEMENTATION-PLAN.md) | “Day 21: MAKS — MTE-tagged KV sharing”; Day 15–16 CXL migrator as implementation days without Axion caveat adjacent. Header already says not Graviton5 fantasy. | Medium | Mark those days **future / capability**; Axion MVP = mmap/NVMe. |
| [`NEXUS_ARM_STEP_BY_STEP_IMPLEMENTATION.md`](../../NEXUS_ARM_STEP_BY_STEP_IMPLEMENTATION.md) | Early line “llama.cpp inference on Graviton”; later correct Axion notes. | Medium | Lead with Axion; Graviton = optional scale-up only. |
| Evidence already honest | [`docs/evidence/latest/MAKS_AUDIT.md`](latest/MAKS_AUDIT.md), [`LAYER_SCORECARD.md`](latest/LAYER_SCORECARD.md), [`docs/haoe/adr/0005-axion-fallbacks.md`](../haoe/adr/0005-axion-fallbacks.md) | — | **Do not dilute** these; prefer linking pitch docs to them. |

### Flags from plan (checklist)

| Flag | Found as demo-as-fact? | Notes |
|------|------------------------|-------|
| Graviton5 / 192 cores / m9g.4xlarge as **the** demo box | **No** in current `00–06` | Still appears as anti-pattern / optional scale-up. Older `plan (1).md` / some how-tos still oriented to Graviton. |
| Native CXL 3.0 / CXL pool as current deployment | **Partial** | Honest in architecture Option A; still assertive in `hackathon_problem_statement.md` + `plan (1).md`. |
| MTE-tagged KV sharing active on GCP instance | **Partial** | Evidence docs say Marketing-only; problem statement Layer 5 still states MTE as the mechanism. |
| NUMA0/NUMA1 split on Axion | **No** (explicitly discouraged) | Good. |
| Benchmark numbers without `benchmarks/` evidence | **Watch** | `05-BENCHMARK-PLAN.md` separates aspirational vs measured — keep that discipline in Devpost. |

---

## Recommended edit batch (after your OK)

1. Soften `hackathon_problem_statement.md` Layer 5 + CXL pillar + rubric wording to “when hardware present / future backends.”  
2. Add a one-line Axion constraint banner to any remaining pitch PDF/source that still leads with multi-NUMA/CXL.  
3. Annotate `plan (1).md` and Day-15/21 sections in `04-IMPLEMENTATION-PLAN.md` as non-demo.  
4. **Do not** change measured numbers in evidence packages.

Reply with confirmation (e.g. “apply Phase B edits”) to proceed with rewrites.
