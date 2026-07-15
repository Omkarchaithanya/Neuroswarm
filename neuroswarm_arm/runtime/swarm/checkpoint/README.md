# Checkpoint Manager — runtime Fault-Tolerance Kernel for NEXUS-ARM

Immutable recovery points for deterministic workflow resume on GCP Axion ARM64.

**Not** a pickle serializer. **Not** a save/load utility. **Not** workflow persistence.

Execution finishes a step → Checkpoint Manager observes → creates an immutable
recovery point. On failure → plan restore → resume instead of restarting the
entire workflow.

```
User → ARMORA → HAOE → Task Graph → Agent Registry → Swarm Context
     → Workflow Coordination → Execution → Experience Store
     → Checkpoint Manager (observer / Fault-Tolerance Kernel)
```

## Name collision

| Package | Class | Purpose |
|---------|-------|---------|
| `neuroswarm_arm.runtime.swarm.checkpoint` | `CheckpointManager` | Durable recovery points + planning |
| `neuroswarm_arm.runtime.swarm.meta_orchestrator` | `CheckpointCoordinator` | Coordination via `ICheckpointManagerPort` |
| `neuroswarm_arm.runtime.swarm.context` | `CheckpointMetadata` | Context-local metadata (no I/O) |
| `neuroswarm_arm.runtime.swarm.experience` | `CheckpointRef` | External ref on execution records |

Import explicitly:

```python
from neuroswarm_arm.runtime.swarm.checkpoint import (
    CheckpointManager,
    CheckpointBuilder,
    build_checkpoint_manager,
)
```

## Architecture

Append-only in-memory (optional JSONL) repository + TTL cache.

- **Manager** validates → appends → caches → emits `CheckpointCreated`
- **Snapshots** store **references only** (graph / execution / context / budget / metrics)
- **RecoveryPlanner** produces deterministic `RecoveryPlan` — **no execution**
- **RollbackMetadataBuilder** records rollback targets — **no undo**
- **PolicyEngine** decides *whether* to checkpoint from observations
- **Retention** archives / expires / compacts envelopes — **no deletion by default**

### Invariants

1. Checkpoint bodies are frozen Pydantic models with `checksum`
2. Repository rejects update/delete of bodies (append-only)
3. No circular imports into HAOE / DIPA / ARMORA / Mem0 — Protocol ports only
4. Implements `ICheckpointManagerPort.create` / `restore` for Meta Orchestrator

## Checkpoint model

Primary unit: `Checkpoint` — `checkpoint_id`, `workflow_id`, `execution_id`,
`parent_checkpoint`, `checkpoint_level`, snapshots, artifact refs, experience /
trace refs, `version`, `checksum`, `metadata`, `status`.

### Levels

`workflow` · `subgraph` · `node` · `manual` · `automatic` · `periodic` ·
`barrier` · `distributed_future` (reserved)

## Snapshot model

| Snapshot | Contents |
|----------|----------|
| `GraphSnapshot` | graph_id, node statuses, frontier |
| `ExecutionSnapshot` | progress + experience snapshot handle |
| `ContextSnapshot` | context_id + context snapshot id / hash |
| `BudgetSnapshot` | envelope remnants (scalars) |
| `MetricsSnapshot` | counters / gauges |

No binary object serialization. No live threads.

## Recovery planning

```python
from neuroswarm_arm.runtime.swarm.checkpoint import FailureContext, build_checkpoint_manager

mgr = build_checkpoint_manager()
plan = mgr.plan_recovery(
    FailureContext(
        workflow_id="wf_1",
        execution_id="ex_1",
        failed_nodes=["n_3"],
        reason="node_timeout",
    )
)
# plan.strategy ∈ resume_checkpoint | resume_node | resume_subgraph |
#                 restart_workflow | rollback_notify
```

## Rollback model

`RollbackRecord` + `RollbackHistory` — target checkpoint / nodes, reason, depth.
Notification metadata only; Meta Orchestrator owns coordination notify path.

## Retention

```python
from datetime import timedelta
from neuroswarm_arm.runtime.swarm.checkpoint import RetentionPolicy

mgr.apply_retention(
    RetentionPolicy(max_age=timedelta(days=7), max_active_per_execution=20)
)
```

## Policies

`Always` · `EveryNNodes` · `EveryNSeconds` · `BeforeTool` · `AfterTool` ·
`BeforeAggregation` · `Manual` · `Custom` predicate.

## Builder API

```python
from neuroswarm_arm.runtime.swarm.checkpoint import (
    CheckpointBuilder,
    ExecutionSnapshot,
    CheckpointLevel,
)

ckpt = (
    CheckpointBuilder()
    .workflow("wf_1", execution_id="ex_1")
    .execution(snapshot=ExecutionSnapshot(execution_id="ex_1", workflow_id="wf_1"))
    .level(CheckpointLevel.BARRIER)
    .build()
)
```

## Integration ports (interfaces only)

| Consumer | Port |
|----------|------|
| Meta Orchestrator | `ICheckpointManagerPort` |
| Experience Store | `ICheckpointExperiencePort` / `IExperienceStorePort` |
| ARMORA | `IArmoraCheckpointPort` |
| HAOE | `IHaoeCheckpointPort` |
| Task Graph | `ITaskGraphCheckpointPort` |
| Agent Registry | `IAgentRegistryCheckpointPort` |
| Swarm Context | `ISwarmContextCheckpointPort` |
| Workflow Coordination | `IWorkflowCoordinationCheckpointPort` |
| Dashboard | `IDashboardCheckpointPort` |
| Performix | `IPerformixCheckpointPort` |
| Policy Engine | `IPolicyEngineCheckpointPort` |

Wire at composition root:

```python
from neuroswarm_arm.runtime.swarm.checkpoint import build_checkpoint_manager
from neuroswarm_arm.runtime.swarm.meta_orchestrator import build_meta_orchestrator

ckpt = build_checkpoint_manager()
orch = build_meta_orchestrator(checkpoint_manager=ckpt)
```

## Extension points

- Custom `ICheckpointRepository` (e.g. GCS / Spanner)
- `register_migration` for schema bumps
- Custom `CheckpointPolicy` predicates
- EventBus subscribers → OpenTelemetry exporters
- Cache TTL / size for hot restore paths

## Future distributed checkpoints

`CheckpointLevel.DISTRIBUTED_FUTURE` is reserved. Replication, cross-region
quorum, and barrier consensus are **out of scope** for this package.

## Quick start

```python
from neuroswarm_arm.runtime.swarm.checkpoint import build_checkpoint_manager

mgr = build_checkpoint_manager()
cid = mgr.create(
    {
        "workflow_id": "wf_1",
        "execution_id": "ex_1",
        "completed_nodes": ["n_1", "n_2"],
        "snapshot_ref": "exp://snapshot/snap_abc",
    }
)
payload = mgr.restore(cid)
assert payload["checkpoint_id"] == cid
```
