# NEXUS-ARM Runtime Model Resilience Engine (RMRE)

Production-grade runtime decision engine for continuous model / backend /
quantization / context / thread / reasoning / tool / cascade resilience on GCP
Axion ARM64.

**Not** simplistic “model unavailable → swap”. RMRE reconciles execution plans
against live health, budgets, and hardware constraints, then emits an optimal
**alternative execution plan** while minimizing quality degradation.

Never executes inference. Never schedules CPU threads. Never owns ARMORA planning.

```
User → ARMORA → Execution Planner → HAOE → DIPA → RMRE → Inference Backend
```

Think: Kubernetes ReplicaSet reconciliation · Envoy circuit breaking ·
service-mesh failover · Temporal retry policies — applied to **execution plans**.

---

## Architecture

```text
RuntimeSignals + ExecutionSnapshot + ModelCatalog
        │
        ▼
   HealthEngine ──► HealthReport
        │
   PolicyEngine ──► ResiliencePolicy
        │
   ResilienceEvaluator ──► CONTINUE | need transition
        │
   CandidateGenerator ──► FallbackCandidate[]
        │
   ConstraintSolver ──► valid candidates
        │
   DeterministicScorer ──► ScoredCandidate[] (stable sort)
        │
   ResiliencePlanner ──► AlternativeExecutionPlan
        │
   RecoveryOrchestrator ──► RecoveryHistory + Events + Metrics
        │
        ▼
   ResilienceDecision (CONTINUE | TRANSITION | DEGRADE_NOTIFY)
```

### Boundary vs peers

| Concern | Owner |
|---------|-------|
| Continuous health/policy → alternative plan | **RMRE** |
| Retry / circuit / call backend / degraded text | DIPA `recovery/` |
| Speculative accept/escalate | ASCR |
| Admit-time budget ladder | ARMORA budget |
| Reasoning-token sensors | RTG (feeds RMRE via signals/ports) |

DIPA wiring is **not** changed in this package. Callers apply
`AlternativeExecutionPlan.to_plan_patch()` when ready.

---

## Fallback model

Eight independently configurable dimensions (`FallbackDimension`):

1. **Model tier** — chain e.g. Qwen3-8B → Qwen3-3B → Phi-4 Mini → Gemma → TinyLlama
2. **Backend** — `llama_cpp` / `sglang` / `vllm` / …
3. **Quantization** — quality ladder (`Q5_K_M` → `Q4_K_M` → …)
4. **Context length** — shrink/fit to need ≤ model max
5. **Thread count** — ≤ available threads
6. **Reasoning budget** — cut reasoning tokens under pressure
7. **Tool usage** — disable tools when not required
8. **Cascade strategy** — `sequential` / `parallel_score` / `least_degradation`

---

## Policies

`ResiliencePolicy` is declarative — **no hardcoded routing** in the engine.

```python
from neuroswarm_arm.runtime.resilience import ResiliencePolicy, build_resilience_engine

policy = ResiliencePolicy(
    policy_id="coding",
    preferred_models=["Qwen3-8B", "Qwen3-3B", "Phi-4-Mini"],
    fallback_chains={"Qwen3-8B": ["Qwen3-3B", "Phi-4-Mini"]},
    backend_preferences=["llama_cpp", "sglang"],
    quantization_preferences=["Q5_K_M", "Q4_K_M"],
    max_latency_ms=3000,
    failure_threshold=1,
    min_health_score=0.55,
    priority=10.0,
)
engine = build_resilience_engine(policies=[policy], catalog=catalog)
```

`PolicyEngine.match` selects highest-priority matching policy. Optional
`IPolicyEnginePort` for external predicates.

---

## Candidate generation

`CandidateGenerator` expands policy chains × enabled dimensions, deduplicates,
and emits `CandidateGenerated` events. Deterministic ordering.

---

## Scoring

`DeterministicScorer` — pure weighted sum (no ML):

quality · latency · cost · memory · policy_priority · health · availability ·
backend_compat · budget_fit · context_compat

Stable tie-break: `(-score, model_id, backend, quant)`.

Weights live on `ResiliencePolicy.score_weights` (`ScoreWeights`).

---

## Constraint solving

`ConstraintSolver` hard-rejects on:

budget · latency · memory · backend · quantization · context · tools · threads

---

## Public APIs

```python
from neuroswarm_arm.runtime.resilience import (
    build_resilience_engine,
    ExecutionSnapshot,
    RuntimeSignals,
    DecisionKind,
)

engine = build_resilience_engine(catalog=profiles, policies=[policy])

decision = engine.evaluate(
    ExecutionSnapshot(execution_id="ex1", model="Qwen3-8B", backend="llama_cpp"),
    RuntimeSignals(model_available=False, historical_failures=2),
)

if decision.kind == DecisionKind.TRANSITION:
    patch = decision.alternative.to_plan_patch()  # DIPA ExecutionPlan field names
    # dipa_port.apply_plan_patch("ex1", patch)

alt = engine.propose(plan, signals)          # AlternativeExecutionPlan | None
decision = await engine.aevaluate(plan, signals)
```

### Key types

| Type | Role |
|------|------|
| `ModelProfile` | Versioned model capability / cost / health profile |
| `ExecutionSnapshot` | RMRE view of active plan |
| `AlternativeExecutionPlan` | Patch + deltas + score |
| `ResilienceDecision` | CONTINUE / TRANSITION / DEGRADE_NOTIFY |
| `RecoveryRecord` | Append-only history entry |
| `HealthReport` | Aggregate health score + factors |

### Factory

`build_resilience_engine(*, policies, catalog, history, events, metrics, experience, performix, external_policy, default_policy_obj)`

---

## Extension points

1. **Custom policies** — `engine.register_policy(...)`
2. **Custom profiles** — `engine.register_profile(...)`
3. **Score weights** — override `ScoreWeights` on policy
4. **Dimension toggles** — `FallbackDimensionConfig(enabled=False)`
5. **External predicates** — `IPolicyEnginePort`
6. **Event / metrics sinks** — subscribe `EventBus` / read `ResilienceMetrics`
7. **Schema migrations** — `register_migration(from_version, fn)`
8. **DI swap** — inject custom `HealthEngine` / `DeterministicScorer` / …

SOLID + constructor DI throughout. Async-friendly via `aevaluate`.

---

## Future RL / GEPA integration

RMRE **does not train**. Recovery history + Experience Store refs expose
`(state=signals+plan, action=alternative, reward≈-quality_delta, …)` features for:

- Offline RL datasets (swarm Experience Store / AROP)
- GEPA / policy evolution proposing new `ResiliencePolicy` versions
- Performix degradation samples via `IPerformixResiliencePort`

Online learning stays out of scope.

---

## Future integration points

| Peer | Port / seam |
|------|-------------|
| **ARMORA** | `IArmoraResiliencePort` — remaining budget dims; admit-time ladder stays ARMORA |
| **HAOE** | `IHaoeResiliencePort` — observe execution only |
| **DIPA** | `IDipaResiliencePort.apply_plan_patch` + `to_plan_patch()`; later wrap `RecoveryStack` |
| **Task Graph** | `ITaskGraphResiliencePort` — workload hints |
| **Swarm Context** | `ISwarmContextResiliencePort` — context tokens / tools |
| **Experience Store** | `IExperienceStorePort.store_snapshot` on recovery |
| **Checkpoint Manager** | `ICheckpointManagerPort` — optional recovery-point ref |
| **Dashboard** | `IDashboardResiliencePort` + `ResilienceMetrics.snapshot` |
| **Performix** | `IPerformixResiliencePort.record_resilience_sample` |
| **Benchmark Runtime** | `IBenchmarkRuntimePort.export_benchmark_row` |
| **Policy Engine** | `IPolicyEnginePort.evaluate_predicate` |
| **GEPA / AROP** | consume history datasets; propose immutable policy versions |

---

## Architectural decisions

1. **Standalone package** under `neuroswarm_arm/runtime/resilience/` — mirrors Checkpoint/Rollback patterns.
2. **Pydantic v2 frozen models** — strong typing, validation, serialization.
3. **Protocol ports only** — no concrete HAOE/DIPA/ARMORA imports.
4. **No DIPA rewire this release** — avoid breaking `IRuntime` / `RecoveryStack` / `ExecutionPlan` APIs.
5. **Deterministic scoring** — reproducible plans for tests / audits.
6. **Plan patch compatibility** — `to_plan_patch()` uses DIPA field names (`model`, `backend`, `quant`, `fallbacks`, `metadata`).
7. **Append-only recovery history** — Experience Store refs, not mutation of peer stores.

---

## Complete file tree

```text
neuroswarm_arm/runtime/resilience/
  __init__.py
  engine.py
  planner.py
  policy.py
  health.py
  candidates.py
  scoring.py
  evaluator.py
  fallback.py
  constraints.py
  recovery.py
  backend.py
  quantization.py
  context.py
  reasoning.py
  threads.py
  execution.py
  metrics.py
  history.py
  serializer.py
  validators.py
  interfaces.py
  models.py
  events.py
  exceptions.py
  versioning.py
  _utils.py
  README.md

tests/resilience/
  __init__.py
  conftest.py
  test_health.py
  test_fallback.py
  test_candidates.py
  test_constraints.py
  test_policy.py
  test_scoring.py
  test_evaluator.py
  test_engine.py
  test_serialization.py
  test_versioning.py
  test_history.py
  test_validators.py
  test_port_contract.py
  test_perf.py
```

---

## Events

`FallbackTriggered` · `CandidateGenerated` · `PolicyMatched` ·
`RecoveryCompleted` · `RecoveryFailed` · `HealthChanged`

## Metrics

`fallback_count` · `success_rate` · `average_degradation` ·
`latency_improvement` · `cost_reduction` · `backend_transitions` ·
`quantization_transitions`

## Serialization

JSON / YAML via `ResilienceSerializer` + `schema_version` migration
(`migrate_payload` / `register_migration`).
