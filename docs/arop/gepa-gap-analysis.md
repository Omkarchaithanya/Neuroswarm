# GEPA Gap Analysis — Official vs NEXUS-ARM

> Validation artifact. Official source: [gepa-ai/gepa](https://github.com/gepa-ai/gepa), [gepa-ai.github.io/gepa](https://gepa-ai.github.io/gepa/), arXiv:2507.19457.

## Naming

| Term | Meaning |
|------|---------|
| NEXUS Layer 5 | MAKS (KV control plane) — unchanged |
| ArmCascade / ASCR | Cascade engine — no GEPA code; future PPO for thresholds |
| Plane 5 / AROP | Autonomic Runtime Optimization Plane — GEPA lives here as Reflection subsystem |
| Official GEPA | Genetic-Pareto reflective evolution of **textual** components |

## Verdict

**Pre-alignment implementation did NOT match official GEPA.**

It was a propose-only stub (`GEPAReflectionStrategy`) that re-labeled rule-based **numeric knob** deltas as `source="gepa"`.

## Official GEPA lifecycle

```
Select from Pareto → Execute minibatch → ASI traces → LLM Reflect
→ Reflective Mutation → Accept if improved → Candidate Pool + Pareto
→ (optional) System-Aware Merge
```

Candidate = `dict[str, str]` named text components. Adapter = `evaluate` + `make_reflective_dataset`.

## Gap matrix

| Module / concept | Status | Why |
|------------------|--------|-----|
| Official `gepa` engine / `optimize()` | Missing | Package not installed; no engine loop |
| `GEPAAdapter` (`evaluate` + `make_reflective_dataset`) | Incorrect | “Adapter” name used for AROP deployment knob adapters |
| Candidate = `dict[str, str]` text | Incorrect | Used `RuntimePolicy` numeric knobs |
| Reflective mutation | Incorrect | Duck-typed hook unused; propose = rule heuristics |
| System-aware merge | Missing | Only `clamp_parameters` knob merge |
| Pareto frontier | Missing | Single-candidate pipeline |
| Candidate pool / lineage / mutation history | Partial | `PolicyRegistry` versions policies, not text candidates |
| ASI builder | Partial | `gepa_asi()` exists; not fed into reflective dataset |
| Evaluation minibatch + valset | Missing | Replay scored synthetic knobs |
| Text-only optimization targets | Incorrect | GEPA path proposed thresholds / draft_len |
| Performix as observation only | Matches | ObservationProvider; never optimizes |
| Propose-only vs deploy | Partial | AROP SafetyGate OK; wrong artifact type |
| Mem0 GEPA candidate schema | Partial | Evolution namespace; not GEPA candidates |
| OKF prompt/playbook versioning | Partial | Policy markdown; not component versions |
| Approval gate for text deploy | Missing | No explicit Approval before GEPA promote |
| ArmCascade redesign | N/A | Correctly untouched |

## Philosophy violations (fixed by this refactor)

1. Labeling rule-based threshold knobs as “GEPA”
2. Treating GEPA as RL / hardware / NUMA / thread optimizer
3. Direct Reflect → Deploy without Pareto / mutation / merge

## Target mapping

| Official concept | NEXUS path |
|------------------|------------|
| `gepa.core.adapter.GEPAAdapter` | `evolution/reflection/gepa/adapter.py` |
| `EvaluationBatch` | `evolution/reflection/gepa/evaluation/batch.py` |
| Reflective mutation | `evolution/reflection/gepa/mutation/reflective.py` |
| System-aware merge | `evolution/reflection/gepa/merge/system_aware.py` |
| Pareto front | `evolution/reflection/gepa/pareto/front.py` |
| Candidate pool | `evolution/reflection/gepa/candidate/pool.py` |
| ASI / reflective dataset | `evolution/reflection/gepa/asi/` |
| `gepa.optimize` (optional) | Soft bridge in `adapter.py` — CI uses local loop |

Numeric knobs remain **non-GEPA** via `RuleBasedReflectionStrategy` only.
