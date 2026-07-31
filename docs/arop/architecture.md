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
