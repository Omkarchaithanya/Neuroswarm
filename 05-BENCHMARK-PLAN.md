# Benchmark Plan — Prove Every Claim

> Replace targets with **measured** Axion numbers. Under-claim beats hype.

---

## Required: Arm Performix (GA recipes only)

Hackathon rules name Performix. Capture via host `apx` + `PerformixClient`:

```bash
apx recipe list
bash performix_capture.sh
# publishes to docs/evidence/performix/
```

| # | Recipe id | Why |
|---|---|---|
| 1 | `code_hotspots` | Flame / function attribution |
| 2 | `cpu_microarchitecture` | Topdown (frontend/backend bound) |
| 3 | `instruction_mix` | **SIMD / SVE2 / I8MM proof** (Arm’s own NEON example recipe) |
| 4 | `memory_access` | SPE load/store latency |
| 5 | `system_characterization` | ASCT preview — platform bring-up |

**Removed:** `system-utilization` (does not exist).  
**CLI truth:** current `apx` uses `recipe run <id> --json` → `run export` (see `performix_client.py`). Do not document fake `--output` / `--duration` as primary flags.

### Stock vs KleidiAI

```bash
# Baseline
NSA_LLAMA_IMAGE=ghcr.io/ggml-org/llama.cpp:server docker compose up -d --force-recreate tier1 tier2 tier3
OUT_DIR=benchmarks/results/performix/stock bash performix_capture.sh

# Optimized
bash scripts/deploy-kleidiai-tiers.sh
OUT_DIR=benchmarks/results/performix bash performix_capture.sh
COMPARE=1 bash performix_capture.sh
```

Expect Instruction Mix / hotspots to show higher SIMD/I8MM share on Kleidi image.

---

## Application benches (real JSON)

```bash
uv sync --all-groups
uv run python benchmarks/run_all.py --out benchmarks/results/run_all.json
# or full evidence pack:
bash scripts/capture-evidence.sh
```

Key scripts:

| Script | Proves |
|---|---|
| `cascade_acceptance.py` | ASCR accept rate / latency |
| `router_accuracy.py` | Top-K tool routing |
| `governor_tokens.py` | RTG token caps |
| `kv_*.py` | KV share / compress / latency |
| `economics.py` | tokens/$ model |

Publish copies under `docs/evidence/latest/` (gitignored raw dir: `benchmarks/results/`).

---

## Topology honesty

On Axion `c4a-standard-8`:

```bash
numactl --hardware   # expect 1 node
lscpu | grep -i numa
```

Do **not** claim measurable NUMA-split speedup on this VM. Claim adaptive HAL + Option A wording.

---

## Target → measured table (fill before submit)

| Claim | Target (aspirational) | Measured (Axion) | Artifact |
|---|---|---|---|
| Cascade latency / accept | — | ASCR accept **~0.42**; sample chat ~66s / tier3; cascade_acceptance tier_used=2 | `prometheus-metrics.txt`, `chat-completion.json`, `run_all.json` |
| Router schema reduction | ≥90% | **16%** avg token reduction (route top-k); tools-route sample **47%** prompt token cut; top-1 **83%**, top-3 **100%**; **6** tools indexed | `run_all.json` / `tools-route.json` |
| Kleidi vs stock tok/s | >1× | Kleidi image proven live (`nexus-arm/llama-kleidiai:server`); full tok/s A/B still optional | `kleidiai-runtime-gate.txt`, `docker-compose-ps.txt` |
| Instruction Mix SIMD share | up vs stock | Kleidi static mix: **Advanced SIMD (NEON) 1.61%** + **SVE 0.34%** (~**1.95%** SIMD-class); integer 44.4% / load-store 27.7% | `static_instruction_mix.csv`, `02-instruction_mix.json` |
| $/1M tokens vs H100 spot | ≥3.5× | sample RCIS **~$0.0016**/req; economics savings score **0.57** (under-claim; not H100 A/B yet) | `chat-completion.json`, `run_all.json` economics |

---

## Reproduce for judges

```bash
uv sync --all-groups
cp .env.example .env
bash scripts/deploy-kleidiai-tiers.sh
bash scripts/capture-evidence.sh
bash performix_capture.sh   # requires apx + Arm account
```
