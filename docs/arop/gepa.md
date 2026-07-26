# GEPA in NEXUS-ARM (Plane 5 Reflection)

Official GEPA: [gepa-ai/gepa](https://github.com/gepa-ai/gepa) · [docs](https://gepa-ai.github.io/gepa/) · arXiv:2507.19457

## What GEPA is here

Genetic-Pareto **text** evolution subsystem under AROP Plane 5:

`neuroswarm_arm/evolution/reflection/gepa/`

Lifecycle: Select Pareto → Execute → ASI → Reflect → Mutate → Accept → Merge → **Approval** → OKF/Mem0 deploy.

## What GEPA is not

- Not RL / PPO / SAC
- Not hardware / NUMA / thread / KleidiAI optimizer
- Not ArmCascade redesign
- Not MAKS (NEXUS Layer 5)
- Not numeric knob tuner (`draft_len`, `accept_threshold`, `router_top_k`, expand threshold → `RuleBasedReflectionStrategy` / AROP knobs)
- Not the tuner of `NSA_ROUTER_HIGH_CONF_GATE` / thinking budget — those stay config + RuleBased if wired

Official `gepa` package is an **optional soft bridge** (`OfficialGEPABridge`); CI/local loops use the in-repo NEXUS GEPA under `evolution/reflection/gepa/`.

## Key types

| Type | Official map |
|------|----------------|
| `NexusGEPAAdapter` | `gepa.core.adapter.GEPAAdapter` |
| `EvaluationBatch` | `gepa.core.adapter.EvaluationBatch` |
| `TextCandidate` | `dict[str, str]` candidate |
| `ParetoFront` | Pareto tracker / SelectCandidate |
| `ReflectiveMutationEngine` | Reflective mutation proposer |
| `SystemAwareMergeEngine` | System-aware merge |
| `ASIBuilder` | ASI / reflective dataset |
| `ApprovalGate` | NEXUS safety (not in upstream GEPA) |

## API

```python
from neuroswarm_arm.evolution.reflection.gepa import GEPAFacade, ApprovalGate, TextArtifactDeployer

facade = GEPAFacade()
result = facade.run_local_loop(
    {"system_prompt": "You are helpful."},
    trainset=[{"id": "1", "input": "q", "expected": "a"}],
)
gate = ApprovalGate()
gate.submit(result.best)
gate.approve(result.best.id)
TextArtifactDeployer(okf_root="okf").deploy(result.best.mark_approved(), gate=gate)
```

Via AROP: `build_arop(...).gepa` · `NSA_AROP_REFLECTION=gepa|hybrid|rule`

## Gap analysis

See [gepa-gap-analysis.md](gepa-gap-analysis.md) and ADR [0004-gepa-text-only.md](adr/0004-gepa-text-only.md).
