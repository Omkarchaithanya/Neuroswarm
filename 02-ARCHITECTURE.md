# Architecture — NeuroSwarm-Arm

> Unified 5-plane design (+ Plane 3.5 speculative tool engine). **Demo hardware = GCP Axion.** Multi-NUMA/CXL are capabilities, not assumed hosts.

---

## Stack overview

```
╔══════════════════════════════════════════════════════════════════╗
║  PLANE 5 · AROP — Performix / OTel / GEPA closed-loop tuning     ║
╠══════════════════════════════════════════════════════════════════╣
║  PLANE 4 · HAOE + semantic MCP router + RTG + AWPP + MAKS        ║
╠══════════════════════════════════════════════════════════════════╣
║  PLANE 3.5 · Speculative tool engine (predict ∥ cascade → MCP)   ║
║              ToolOutputCache.make_key · optional when ENABLED    ║
╠══════════════════════════════════════════════════════════════════╣
║  PLANE 3 · DIPA / ASCR cascade — KleidiAI llama.cpp tiers        ║
║            Tier1 0.5B → Tier2 3B → Tier3 8B (Compose/Helm)       ║
║            Optional SGLang CPU prefill (profile `pd`)            ║
╠══════════════════════════════════════════════════════════════════╣
║  PLANE 2 · Shared KV + Mem0 + OKF                                ║
║            CXL / MTE paths activate only when topology HAL says  ║
╠══════════════════════════════════════════════════════════════════╣
║  PLANE 1 · Topology HAL (NUMA / CXL / MTE / ISA flags)           ║
║            Demo: Axion c4a Neoverse-V2 · Scale-up: multi-socket  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## PLANE 1 — Hardware (Option A)

**Canonical pitch:** NeuroSwarm-Arm auto-detects NUMA/CXL/MTE at runtime and degrades safely on single-NUMA VMs like **GCP Axion `c4a-standard-8`**, while activating NUMA-split cascades and CXL KV pooling on multi-socket Neoverse hosts (e.g. AWS Graviton4/5 `.16xlarge+`).

| Host | Role | Topology |
|---|---|---|
| GCP Axion `c4a-standard-8` | **Primary demo / evidence** | Neoverse-V2, 8 vCPU, 32 GB, **1 NUMA**, SVE2/I8MM/BF16, no CXL |
| Graviton4/5 multi-NUMA | Optional scale-up | NUMA-split + CXL when present |

HAOE/DIPA providers already degrade (see `docs/haoe/adr/`, README). Do **not** hardcode `numactl --cpunodebind=0/1` as the Axion demo path.

**KleidiAI build (required for Arm proof):**

```bash
# docker/Dockerfile.llama-kleidiai
cmake -B build -DGGML_CPU_KLEIDIAI=ON -DGGML_NATIVE=ON -DGGML_OPENMP=ON ...
# Image: nexus-arm/llama-kleidiai:server
bash scripts/deploy-kleidiai-tiers.sh
```

---

## PLANE 2 — KV / memory

- Shared KV + Mem0 + OKF on all hosts.
- **CXL / MTE:** capability flags from topology HAL. On Axion → NVMe/mmap fallback (honest). On multi-socket / AGI paths → CXL + MTE when available.
- Risk R5 (07): treat CXL as forward-compatible, not Axion headline.

---

## PLANE 3 — Inference (DIPA / ASCR)

- Default decode: **KleidiAI llama.cpp** tiers via Compose.
- Cascade: confidence-gated escalate 0.5B → 3B → 8B.
- Optional prefill: SGLang with `SGLANG_USE_CPU_ENGINE=1` (Arm Neoverse contribution, May 2026). Pin multi-arch `lmsysorg/sglang` tag; verify arm64 before claiming.

---

## PLANE 3.5 — Speculative tool engine

Sits **between** HAOE/router (Plane 4) and DIPA/ASCR decode (Plane 3): after Top-K tool schemas are chosen, `SpeculativeEngine` may run a draft predictor in parallel with cascade generation and fire MCP early into `ToolOutputCache`.

Canonical cache key (do not invent another hash):

`ToolOutputCache.make_key(tool_name, args)` → `sha256(f"{tool_name}:{canonical_json(args)}")[:32]`  
(`neuroswarm_arm/runtime/dipa/speculative/tool_cache.py`)

Papers: arXiv:2512.15834 (Nichols), arXiv:2510.04371 (Ye). Default-on in compose via `NSA_TOOL_SPEC_ENABLED=1`; live Axion gateway must be rebuilt before `/v1/tools/cache` answers (404 until redeploy).

```text
gateway → HAOE → router Top-K
              └─► SpeculativeEngine (Plane 3.5)
                    ├─ predictor(T1) ─► executor(MCP) ─► ToolOutputCache.make_key
                    └─ DIPA/ASCR gen(T2/3) ─► match tool_call → reuse cache / else sync MCP
                         └─► tier llama-server → metrics
```

---

## PLANE 4 — Orchestration

- HAOE task graphs; semantic MCP router (TurboVec / Top-K); RTG; AWPP; MAKS connectors.
- Affinity: best-effort; no-op when single NUMA.

---

## PLANE 5 — AROP / Performix

Product path: host `apx` via `performix-bridge` (`profiles: ["performix"]`).  
IDE toolbox: `armlimited/arm-mcp:latest` (repo `github.com/arm/mcp`).

**GA recipes only:**

| Recipe id | Why |
|---|---|
| `code_hotspots` | Flame / function attribution |
| `cpu_microarchitecture` | Topdown stalls |
| `instruction_mix` | **SVE2 / I8MM / SIMD proof** |
| `memory_access` | SPE load/store |
| `system_characterization` | ASCT preview |

Capture: `bash performix_capture.sh` → `docs/evidence/performix/`.

---

## Request path

```
gateway → HAOE graph → router Top-K
       → [optional] SpeculativeEngine (predict ∥ cascade; cache via ToolOutputCache.make_key)
       → DIPA/ASCR → tier llama-server → metrics (RMF/Prometheus)
```

Evidence scripts: `scripts/capture-evidence.sh`, `scripts/deploy-kleidiai-tiers.sh`, `benchmarks/speculative_tool_bench.py`.
