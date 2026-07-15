# Rollback Manager — runtime Transaction & Recovery subsystem for NEXUS-ARM

Deterministic workflow consistency restoration after partial execution failures
on GCP Axion ARM64.

**Not** checkpoint restore. **Not** save/load. **Not** `undo()`.

Think Temporal Workflow Replay. Think Saga Compensation. Think Kubernetes
Reconciliation. Think Database Transaction Rollback.

```
User → ARMORA → HAOE → Task Graph → Agent Registry → Swarm Context
     → Workflow Coordination → Execution → Checkpoint Manager
     → Recovery Planner → Rollback Manager (this package)
```

## Name collision

| Package | Class | Purpose |
|---------|-------|---------|
| `neuroswarm_arm.runtime.swarm.rollback` | `RollbackManager` | Consistency restore + plan/validate/apply descriptors |
| `neuroswarm_arm.runtime.swarm.checkpoint` | `RollbackMetadataBuilder` | Notify-only rollback metadata (unchanged) |
| `neuroswarm_arm.runtime.swarm.meta_orchestrator` | `RollbackCoordinator` | Coordination notify only (unchanged) |
| `neuroswarm_arm.runtime.swarm.checkpoint` | `RecoveryPlanner` | Where to resume (inputs to this package) |

Import explicitly:

```python
from neuroswarm_arm.runtime.swarm.rollback import (
    RollbackManager,
    RollbackBuilder,
    build_rollback_manager,
)
```

## Architecture

Append-only in-memory (optional JSONL) repository + history store.

- **Manager** plans → validates → prepares → applies → records history
- **Strategies** are pure objects — shape plan fields only, no I/O
- **ConsistencyChecker** detects orphan nodes, invalid checkpoints, version mismatch
- **Policies** decide *whether* to roll back from observations
- **Executor** materializes restored **state descriptors** only — never runs agents

### Invariants

1. Rollback bodies are frozen Pydantic models with `checksum`
2. Repository rejects update/delete of bodies (append-only; status via envelope)
3. No circular imports into HAOE / DIPA / ARMORA / Mem0 — Protocol ports only
4. Implements `IRollbackManagerPort.plan` / `validate` / `execute`

### Division of labor

| Layer | Owns |
|-------|------|
| Checkpoint Manager | Immutable snapshots |
| Recovery Planner | Where recovery begins |
| **Rollback Manager** | How consistency is restored |
| RollbackCoordinator | Notify-only coordination |

## Rollback model

Primary unit: `RollbackOperation` — `rollback_id`, `workflow_id`, `execution_id`,
`checkpoint_reference`, `recovery_plan_reference`, `rollback_strategy`,
`rollback_level`, `rollback_reason`, `initiator`, targets, `metadata`, `status`,
`version`, `history`, `checksum`.

### Levels

`WORKFLOW` · `SUBGRAPH` · `NODE` · `CONTEXT` · `BUDGET` · `EXECUTION_METADATA` ·
`DISTRIBUTED_FUTURE` (reserved)

### Strategies (pure objects)

`RESUME_CHECKPOINT` · `RESTART_WORKFLOW` · `RESTART_NODE` · `RESTART_SUBGRAPH` ·
`ROLLBACK_CONTEXT` · `ROLLBACK_BUDGET` · `ROLLBACK_METADATA` · `CUSTOM`

### Status lifecycle

`PENDING` → `VALIDATED` → `PREPARED` → `COMPLETED` | `FAILED` | `CANCELLED`

## Quick start

```python
from neuroswarm_arm.runtime.swarm.rollback import (
    FailureObservation,
    RollbackBuilder,
    RollbackStrategyKind,
    build_rollback_manager,
)

mgr = build_rollback_manager()

op = (
    RollbackBuilder()
    .workflow("wf_1", execution_id="ex_1")
    .checkpoint("ckpt_1")
    .strategy(RollbackStrategyKind.RESUME_CHECKPOINT)
    .reason("node_timeout")
    .build()
)

plan = mgr.plan(
    FailureObservation(
        workflow_id="wf_1",
        execution_id="ex_1",
        failed_nodes=["n_3"],
        checkpoint_reference="ckpt_1",
        reason="node_timeout",
    )
)
mgr.validate(plan, known_nodes=["n_1", "n_2", "n_3"])
result = mgr.execute(plan)
assert result.status.value == "completed"
```

## Consistency validation

Validates task graph, execution, checkpoint, context, budget, artifact, and
experience references. Detects:

- Orphan nodes
- Invalid checkpoints / recovery plans
- Version mismatch
- Partial failures without checkpoint
- Dangling artifact / experience refs

## Recovery execution metadata

`RecoveryExecutionMetadata` captures recovery order, dependencies, resume node /
workflow / subgraph, rollback depth, and duration. No workflow execution.

## Policies

`Always` · `Manual` · `Automatic` · `Threshold` · `Budget` · `Latency` ·
`Failure` · `Custom` (predicate port)

## Events / metrics

Events: `RollbackStarted`, `RollbackCompleted`, `RollbackFailed`,
`RollbackCancelled`, `RollbackValidated`, `RecoveryPrepared`, `RecoveryFinished`.

Metrics: count, duration, recovery latency, strategy usage, success/failure rate,
consistency violations. OTel attrs under `nexus.swarm.rollback.*`.

## Extension points

- Custom `IRollbackStrategy` / `CustomStrategy`
- Custom `RollbackPolicy` + `IPolicyPredicatePort`
- `register_migration` for schema bumps
- `IRollbackRepository` (InMemory / Jsonl / custom)
- EventBus subscribers / metrics sinks

## Future integration

Composition root (not wired in this package):

```python
ckpt = build_checkpoint_manager()
rb = build_rollback_manager()  # inject ports when adapters land
orch = build_meta_orchestrator(...)
```

| Peer | Port | Future use |
|------|------|------------|
| ARMORA | `IArmoraBudgetRollbackPort` | Budget descriptor restore |
| HAOE | `IHaoeRollbackPort` | Observe execution only |
| Task Graph | `ITaskGraphRollbackPort` | Graph consistency |
| Swarm Context | `ISwarmContextRollbackPort` | Context snapshot refs |
| Workflow Coordination | `IWorkflowCoordinationRollbackPort` | Execution observation |
| Checkpoint Manager | `ICheckpointRollbackPort` | Resolve checkpoints |
| Recovery Planner | `IRecoveryPlannerPort` | Recovery plan refs |
| Experience Store | `IExperienceStoreRollbackPort` | Attach rollback refs |
| Dashboard | `IDashboardRollbackPort` | Export metrics |
| Performix | `IPerformixRollbackPort` | Latency samples |

## Future distributed rollback

`RollbackLevel.DISTRIBUTED_FUTURE` is reserved. Multi-node / cross-region
compensation is explicitly out of scope for this package version.

## Non-goals

- Workflow execution / HAOE scheduling
- DIPA / Mem0 / OKF rollback
- Distributed rollback / Kubernetes
- RL / agent execution
- AROP policy rollback / KV-MAKS tier rollback

## Tests

```bash
pytest tests/rollback -q
```
