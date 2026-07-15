# Experience Store

Immutable historical execution database for the NEXUS-ARM swarm plane.

**Not** a logger. **Not** a conversation history. **Not** a mutable database wrapper.

Execution finishes → Experience Store records everything → GEPA / benchmarking /
policy evolution / dashboards / offline RL **consume**.

```
User → ARMORA → HAOE → Task Graph → Agent Registry → Swarm Context
     → Workflow Coordination → Execution → Experience Store
```

## Name collision

| Package | Class | Purpose |
|---------|-------|---------|
| `neuroswarm_arm.runtime.swarm.experience` | `ExperienceStore` | Completed workflow execution history |
| `neuroswarm_arm.evolution.rl.experience_store` | `ExperienceStore` | AROP offline RL `(s,a,r,s')` tuples |

Import explicitly from the swarm package:

```python
from neuroswarm_arm.runtime.swarm.experience import (
    ExperienceStore,
    ExecutionRecord,
    build_experience_store,
)
```

## Architecture

Append-only JSONL (optional) + in-memory secondary indexes.

- **Recorder** validates → appends → indexes → emits `ExecutionRecorded`
- **QueryEngine** filters by workflow / agent / model / backend / latency / cost / quality / success / date / budget / tags / custom predicates
- **Analytics** aggregates utilization and efficiency
- **Datasets** emit benchmark / policy / offline-RL / analytics feature tables (**no training**)
- **Retention** archives / compacts / prunes envelope metadata — **no deletion by default**
- **Artifacts** store **references only** (outputs, logs, metrics, benchmarks, reports, flamegraphs, Performix)

### Invariants

1. Records are frozen Pydantic models with `content_hash`
2. Repository rejects update/delete
3. No circular imports into HAOE / DIPA / ARMORA / Mem0 — Protocol ports only
4. Implements `IExperienceStorePort.store_snapshot` / `load_snapshot` for Swarm Context

## Execution Record

Primary unit: `ExecutionRecord` — execution_id, workflow_id, plan/graph refs,
agent assignments, models/backends/quantizations, tool calls, latency split,
tokens, resources, cost/energy/budget, quality, success, checkpoints, artifacts,
metrics, telemetry/trace refs, metadata, version, content_hash.

## History model

| Type | Role |
|------|------|
| `ExecutionRecord` | One completed execution |
| `WorkflowRecord` | Workflow rollup linking execution ids |
| `ExecutionPlan` | Planned steps + bindings (definition hash) |
| `RecordEnvelope` | Lifecycle (`recorded` → `archived` → `exported`) around immutable body |

## Dataset generation

```python
store = build_experience_store()
store.record(ExecutionRecord(workflow_id="wf_1", ...))
ds = store.generate_dataset("offline_rl")
store.export_dataset("benchmark", fmt="csv", path="out/bench.csv")
```

Formats: JSON, CSV, Parquet (optional `pyarrow`), OTel-compatible JSON.

## Analytics

`store.compute_analytics()` → average latency/cost/quality, model/agent/backend
utilization, failure rate, retry frequency, budget efficiency.

## Retention

```python
from datetime import timedelta
from neuroswarm_arm.runtime.swarm.experience import RetentionPolicy

store.apply_retention(RetentionPolicy(max_age=timedelta(days=30), max_active_records=10_000))
```

## Future RL / GEPA integration

Offline RL dataset rows expose `(state, action, reward, next_state, done)` features.
Policy dataset rows expose model/backend/agent choices + outcomes for GEPA /
AROP reflection. This package **does not train** or deploy policies.

## Integration ports (interfaces only)

| Consumer | Port |
|----------|------|
| ARMORA | `IArmoraExperiencePort` |
| HAOE | `IHaoeExperiencePort` |
| Task Graph | `ITaskGraphExperiencePort` |
| Agent Registry | `IAgentRegistryExperiencePort` |
| Swarm Context | `ISwarmContextExperiencePort` / `IExperienceStorePort` |
| Workflow Coordination | `IWorkflowCoordinationPort` |
| Checkpoint Manager | `ICheckpointExperiencePort` |
| Dashboard | `IDashboardExperiencePort` |
| Performix | `IPerformixExperiencePort` |
| Benchmark Runtime | `IBenchmarkRuntimePort` |
| Policy Engine / GEPA | `IPolicyEnginePort` |

Live chat path is **not** wired yet — inject `build_experience_store()` at the
composition root when Meta Orchestrator / HAOE completion hooks are ready.

## Quick start

```python
from neuroswarm_arm.runtime.swarm.experience import (
    ExecutionRecord,
    QualityScore,
    build_experience_store,
)

store = build_experience_store()  # or root="/var/lib/nexus/experience"
rec = store.record(
    ExecutionRecord(
        workflow_id="wf_demo",
        latency=42.0,
        estimated_cost=0.01,
        quality_score=QualityScore(execution=0.9, workflow_completion=1.0),
        models_used=["llama-3.1-8b"],
        backends_used=["llamacpp"],
        success=True,
    )
)
assert store.get(rec.execution_id).content_hash
```

## Tests

```bash
pytest tests/experience -q
```
