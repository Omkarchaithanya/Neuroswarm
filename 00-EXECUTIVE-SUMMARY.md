# NeuroSwarm-Arm — Executive Summary

> **One-line pitch:** Self-evolving, cost-optimized multi-agent cloud AI runtime for Arm Neoverse — three-tier CPU cascade + KleidiAI llama.cpp + Arm Performix-driven evolution + semantic MCP router — proven on **GCP Axion**, with hardware-adaptive NUMA/CXL/MTE that activates only when the host exposes it.

**Hackathon:** Arm Create: AI Optimization Challenge 2026 — **Cloud AI track**  
**Deadline:** Aug 14, 2026 16:00 PDT — **submit Aug 13**  
**Prize target:** $1,000 Best in Cloud AI → $3,000 Overall Winner  
**Fallback:** $2,000 Overall Runner-Up

---

## 1. Why this wins (judge-mapping)

| Criterion (weight) | What NeuroSwarm-Arm delivers |
|---|---|
| **Technological Implementation (40)** | `GGML_CPU_KLEIDIAI=ON` llama.cpp image (`nexus-arm/llama-kleidiai:server`), SVE2/I8MM/BF16 on Axion Neoverse-V2, three-tier CPU cascade, semantic MCP router, HAOE/DIPA kernels, **real Arm Performix** recipes (`code_hotspots`, `cpu_microarchitecture`, `instruction_mix`, `memory_access`, `system_characterization`). Topology HAL auto-detects NUMA/CXL/MTE and degrades safely on single-NUMA VMs. |
| **WOW factor (25)** | Live cost dashboard + cascade tier graph + Performix Instruction Mix proof (SIMD/I8MM kernels visible). No GPU. |
| **Potential Impact (20)** | Helm chart + Docker ARM64 + 6 MCP templates + Grafana + OKF seed. Migration path from GPU/x86. |
| **UX / DX (15)** | Compose-first Axion MVP; `helm install` path; judge-zero `docs/setup.md`; &lt;3 min demo video. |

---

## 2. Hardware truth (do not invent)

| Role | Reality |
|---|---|
| **Demo / evidence host** | GCP Axion `c4a-standard-8` (Neoverse-V2, 8 vCPU, 32 GB, **1 NUMA node**, no CXL) |
| **Optional scale-up** | Multi-socket Neoverse (e.g. AWS Graviton4/5 `.16xlarge+`) where NUMA-split + CXL KV activate |

**Option A pitch (canonical):** NeuroSwarm-Arm auto-detects NUMA/CXL/MTE at runtime and degrades safely on single-NUMA VMs like GCP Axion c4a, while activating full NUMA-split cascades and CXL KV pooling on multi-socket Neoverse hosts.

---

## 3. Stack (built, not aspirational)

Planes: HAOE · DIPA/ASCR cascade · AQR/AWPP/MAKS · AROP/Performix · OKF/Mem0.  
Inference: KleidiAI llama.cpp tiers (+ optional SGLang CPU engine on Arm — see Arm May 2026 Neoverse SGLang blog).  
MCP image: `armlimited/arm-mcp:latest` (GitHub repo: `arm/mcp`).

---

## 4. Evidence gates before submit

- [ ] `docker compose ps` shows `nexus-arm/llama-kleidiai:server` (not stock `ghcr.io/ggml-org/llama.cpp:server`)
- [ ] Non-empty `prometheus-metrics.txt` / Grafana scrape
- [ ] `run_all.json` not `"skipped"`
- [ ] Performix `instruction_mix` + `code_hotspots` under `docs/evidence/performix/`
- [ ] Pitch docs match Axion + Option A; 3 judges only; runner-up noted

---

## 5. Timeline reminder

P0 close evidence → P1 measured benches → P2 video → **submit Aug 13**.
