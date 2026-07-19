# Submission Strategy — Win the Judges' Eyes

> README, demo video, Devpost — score all four criteria. Match **Axion evidence**, not Graviton fiction.

---

## Judges (live Devpost — **3 only**)

- **Avin Zarlez** — Arm Staff SW Engineer, Developer Evangelist  
- **Michael Hall** — Arm Principal SW Engineer, Developer Evangelist  
- **Gabriel Peterson** — Arm Senior ML Engineer, Developer Evangelist  

They will check Compose IMAGE tags, `numactl --hardware`, Performix recipe names, and `/metrics`.

---

## Prize tiers

- $1,000 Best in Cloud AI → $3,000 Overall Winner  
- **Fallback: $2,000 Overall Runner-Up**

**Submit Aug 13** (not Aug 14 deadline day).

---

## Project Overview (paste)

> NeuroSwarm-Arm is a self-evolving, cost-optimized multi-agent AI runtime for Arm Neoverse. Three-tier CPU cascade on **KleidiAI** llama.cpp (`nexus-arm/llama-kleidiai:server`), semantic MCP router (6 templates indexed), reasoning-token governor, and Arm Performix with real `code_hotspots` + `instruction_mix` receipts. Live demo on **GCP Axion c4a-standard-8** (1 NUMA — Option A). Auto-detects NUMA/CXL/MTE; activates NUMA-split/CXL only on multi-socket hosts. Helm + Compose + Grafana. Why it wins: evidence matches the pitch.

Full text: `01-PROBLEM-STATEMENT.md` / `docs/DEVPOST-OVERVIEW.md`.

---

## Functionality bullets

1. KleidiAI inference image `nexus-arm/llama-kleidiai:server`  
2. Three-tier CPU cascade (0.5B → 3B → 8B)  
3. Semantic MCP router (Top-K schemas)  
4. Reasoning-token governor  
5. Adaptive topology (NUMA/CXL/MTE)  
6. AROP + Performix GA recipes  
7. Grafana cost / cascade dashboard  
8. Helm chart + Compose MVP  
9. 6 MCP templates  
10. Judge-zero setup (`docs/setup.md`)

---

## Setup (3-line field)

```bash
uv sync --all-groups && cp .env.example .env
bash scripts/deploy-kleidiai-tiers.sh   # on Axion aarch64
curl http://127.0.0.1:8000/health
```

Details: `docs/setup.md`, `docs/gcp-axion-setup.md`.

---

## Demo video (&lt;3 min) — still do it (optional ≠ skip)

| Time | Beat |
|---|---|
| 0:00–0:15 | Cost number cold-open |
| 0:15–0:45 | Live `curl` chat on Axion gateway |
| 0:45–1:30 | Grafana real panels |
| 1:30–2:15 | Performix Instruction Mix / hotspots |
| 2:15–2:45 | `docker compose ps` showing KleidiAI image |
| 2:45–3:00 | Option A one-liner + CTA |

Record on the **actual Axion device**. YouTube/Vimeo/Youku.

---

## Red flags to avoid

| Red flag | Fix |
|---|---|
| Stock `ggml-org/llama.cpp` in evidence | `deploy-kleidiai-tiers.sh` |
| Empty metrics / skipped `run_all` | fixed `capture-evidence.sh` |
| Invented Performix recipes | GA five only |
| “NUMA-split Graviton5” as demo | Option A + Axion |
| 4th judge name | deleted |
| `arm/mcp:latest` Docker tag | `armlimited/arm-mcp:latest` |

---

## Criteria mapping

| Weight | Evidence |
|---|---|
| Tech 40 | KleidiAI + Performix + cascade + CI |
| WOW 25 | Video + dashboard + Instruction Mix |
| Impact 20 | Measured benches + Helm apply + templates |
| UX/DX 15 | setup.md cold clone + helm lint/apply &lt;90s |

Demo video: `docs/DEMO-VIDEO-CHECKLIST.md`. Hygiene: `docs/SUBMISSION-HYGIENE.md`.
