# AROP Architecture (Plane 5)

> **Naming:** NEXUS **Layer 5 = MAKS** (KV control plane). **AROP = Plane 5** Autonomic Runtime Optimization Plane. AROP optimizes policies across Layers 1–5; it does not replace MAKS.

## Pipeline

```
Observe → Normalize → Store → Analyze → Reflect → Generate Candidate Policies
→ Offline Evaluation → Shadow Execution → Statistical Validation → Safety Verification
→ Canary Deployment → Continuous Monitoring → Rollback → Knowledge Update
```

Never: Reflect → Deploy.

## Engines

| Engine | Role |
|--------|------|
| Observation | `ObservationProvider` backends (Performix, OTel, Prometheus, Linux perf, PMU, Runtime) |
| Knowledge | Mem0 runtime memory + OKF engineering memory |
| Reflection | `ReflectionStrategy` — Rule (knobs) / **GEPA (text-only Genetic-Pareto)** / Hybrid / Human |
| Optimization | Materializes immutable `RuntimePolicy` |
| Experiment | Offline / shadow / canary |
| Replay | Episode replay under candidate policies |
| Validation | Multi-metric scorecard + Welch / effect size |
| Safety | SLO / budget / regression gates |
| Deployment | Shadow / canary / promote / rollback + layer adapters |
| Evolution | Policy lineage → OKF |

## Dependency inversion

- GEPA is a **text-only ReflectionStrategy** (official Genetic-Pareto); not a knob deployer. See [gepa.md](gepa.md).
- Performix is an **ObservationProvider**, not the optimizer.
- ASCR consumes policies via `PolicyRegistryBackedAgent` / `RLAction` adapters.

## Package

`neuroswarm_arm/evolution/` — see `factory.build_arop()` and FastAPI `/arop/*`.

## AROP v1 CLI tuner (rule-based, shipping now)

Standalone module [`neuroswarm_arm/arop/`](../../neuroswarm_arm/arop/) — **independent of** the evolution `RuntimeOptimizer` pipeline for v1.

- Rule-based only (no PPO / GEPA / Mem0 in this path).
- Consumes honest `apx` JSON + benchmark outputs; fail-loud on missing/null fields (never invent `0`).
- Dry-run by default: `python -m neuroswarm_arm.arop.evolve_cycle`.
- Live apply restarts **gateway** only (`NSA_ASCR_DRAFT_LEN` / `NSA_ASCR_ACCEPT_THRESHOLD`); no runtime GGUF swap.
- Preflight: `python -m neuroswarm_arm.arop.preflight` / `scripts/arop-preflight.sh` — requires `NSA_PERFORMIX_ALLOW_DEMO=0`, `source=apx`, rejects `posix_fallocate`/low-sample captures; logs CPU features honestly (does not invent KleidiAI/SME2/CSS V3/MTE).
- **Not claimed on Axion MVP:** CSS V3, CXL, MTE, SME2 product acceleration, true P/D disaggregation, or dynamic multi-quant fleets.
- The `neuroswarm_arm/evolution/` Plane 5 pipeline (GEPA, PolicyRegistry, canary) remains scaffolding for a later closed loop — do not treat it as the shipping AROP v1 path.
- **Why no PPO / GEPA-as-knobs / GRPO:** [ADR 0005](adr/0005-rule-based-closed-loop-not-rl.md). Axion cascade stays **0.5B / 3B / 7B Q4** — optimize knobs and KleidiAI, not model scale.
- See [`neuroswarm_arm/arop/README.md`](../../neuroswarm_arm/arop/README.md).

## Config

| Env | Default | Meaning |
|-----|---------|---------|
| `NSA_AROP_ENABLED` | `1` | Enable plane |
| `NSA_AROP_PERFORMIX` | `0` | Real `apx` recipes |
| `NSA_AROP_REFLECTION` | `rule` | `rule\|gepa\|hybrid\|offline_llm` |
| `NSA_AROP_CANARY_PCT` | `10` | Canary traffic % |
| `NSA_AROP_AUTO_PROMOTE` | `0` | Promote after canary |
| `NSA_AROP_MIN_IMPROVEMENT` | `0.01` | Primary metric delta |

## ADR

- [0001-plane5-not-maks.md](adr/0001-plane5-not-maks.md)
- [0002-propose-only-reflection.md](adr/0002-propose-only-reflection.md)
- [0003-immutable-policies.md](adr/0003-immutable-policies.md)
