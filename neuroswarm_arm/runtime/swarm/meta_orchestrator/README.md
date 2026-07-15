# Meta Orchestrator

Production **workflow coordination engine** for **NEXUS-ARM** on GCP Axion ARM64.

Package: `neuroswarm_arm.runtime.swarm.meta_orchestrator`

This is **not** a scheduler, planner, or execution engine.

It coordinates execution between **Task Graph**, **Agent Registry**, **Swarm Context**, **HAOE**, **ARMORA**, and **DIPA**.

## Architecture

```
User
  │
ARMORA          (budget admission)
  │
HAOE            (WHEN — scheduling / workers)
  │
Task Graph      (WHAT)
  │
Agent Registry  (WHO)
  │
Swarm Context   (WHAT EVERY AGENT KNOWS)
  │
Meta Orchestrator  ← THIS PACKAGE (coordination only)
  │
DIPA            (HOW — inference)
  │
Inference
```

Think: Kubernetes Controller · Temporal Workflow Engine · Ray Driver · LangGraph Coordinator.

| Peer | Owns | Meta Orchestrator does |
|------|------|------------------------|
| Task Graph | DAG definition + node lifecycle types | Ready-node discovery via `ReadyNodeResolver` |
| Agent Registry | Capability catalog + selection | Candidate `AgentAssignment` only |
| Swarm Context | Shared operating state | Attach / propagate / merge via ports |
| HAOE | Scheduling + worker pools | Emits `ExecutionRequest` via `IHaoeExecutionPort` |
| ARMORA | Frozen budget envelopes | Reads remaining via `IArmoraBudgetPort` |
| DIPA | Inference | Passes baggage keys via `IDipaHintsPort` only |

### Explicit non-goals

- No planning
- No HAOE scheduling / work-stealing
- No agent execution bodies
- No DIPA inference
- No Mem0 / OKF / KV ownership
- No RL / AROP
- No Kubernetes / distributed runtime

> Note: top-level architecture docs sometimes map “meta-orchestrator” loosely to **AWPP** (pre-warm prediction). **AWPP remains a separate prediction connector.** This package is the **swarm workflow coordinator**.

## Coordination model

```
TaskGraph
   ↓
Ready Nodes        (ReadyNodeResolver)
   ↓
Agent Assignment   (AgentAssigner → candidates)
   ↓
HAOE Execution Request  (Dispatcher → IHaoeExecutionPort)
   ↓
Monitor            (ExecutionMonitor)
   ↓
Update Context
   ↓
Collect Results
   ↓
Aggregator         (ResultAggregator — merge only)
   ↓
Barriers           (BarrierSynchronizer)
   ↓
Next Ready Nodes
   … until complete
```

Async reconcile loop lives in `Coordinator.coordinate` / `Coordinator.step`.

## Workflow lifecycle

```
Created → Ready → Running ⇄ Waiting → Completed
                              ↓
                           Failed / Cancelled
                              ↓
                     Checkpointed → Restored → Ready/Running
```

Enforced by `WorkflowLifecycle` + `WORKFLOW_TRANSITIONS`.

## Synchronization

`BarrierSynchronizer` supports:

- Join nodes (multi-predecessor barriers)
- Parallel fan-out / fan-in
- Aggregation barriers (`NodeType.AGGREGATE`)
- Conditional joins (evaluated with readiness)

## Aggregation

`ResultAggregator` merges:

- outputs
- metadata
- metrics
- budgets
- tool outputs
- memory references

No inference. No summarization. Pure coordination merge.

## Failure coordination

| Action | Module | Behavior |
|--------|--------|----------|
| Retry | `RetryCoordinator` | Emits retry decision; does not sleep/backoff |
| Skip | retry `skip=True` | Node → skipped set |
| Fallback | `fallback_agent_id` on decision | Recorded for HAOE consumers |
| Checkpoint | `CheckpointCoordinator` | Create/restore via ports |
| Rollback | `RollbackCoordinator` | Notification only |

## Public API

```python
from neuroswarm_arm.runtime.swarm.meta_orchestrator import (
    MetaOrchestrator,
    WorkflowBuilder,
    WorkflowExecution,
    WorkflowStatus,
    ReadyNodeResolver,
    AgentAssignment,
    build_meta_orchestrator,
)

orch = build_meta_orchestrator(haoe=my_haoe_port, catalog=my_catalog)

execution = await (
    WorkflowBuilder()
    .graph(task_graph)
    .context(swarm_context)
    .agents(["nexus.agents.coding_agent"])
    .execute(orch)
)
```

## Events

`WorkflowCreated`, `WorkflowStarted`, `NodeAssigned`, `NodeCompleted`, `NodeFailed`,
`WorkflowCompleted`, `WorkflowCancelled`, `CheckpointCreated`, `CheckpointRestored`,
`AggregationFinished`, `RetryRequested`, `RollbackNotified`, `BarrierReleased`.

OTel attribute prefix: `nexus.meta_orchestrator.*`.

## Metrics

| Metric | Name |
|--------|------|
| Workflow latency | `nexus_meta_orchestrator_workflow_latency_ms` |
| Coordination latency | `nexus_meta_orchestrator_coordination_latency_ms` |
| Aggregation time | `nexus_meta_orchestrator_aggregation_ms` |
| Barrier waits | `nexus_meta_orchestrator_barrier_wait_ms` |
| Assignments | `nexus_meta_orchestrator_assignments_total` |
| Retries | `nexus_meta_orchestrator_retry_requests_total` |
| Checkpoints | `nexus_meta_orchestrator_checkpoints_total` |
| Failures | `nexus_meta_orchestrator_node_failures_total` |
| Parallelism gauge | `nexus_meta_orchestrator_parallelism` |

## Extension points

| Port | Purpose |
|------|---------|
| `IHaoeExecutionPort` | submit / poll / cancel execution requests |
| `IAgentCatalogPort` | candidate selection |
| `ISwarmContextPort` | attach / evolve / merge context |
| `IArmoraBudgetPort` | frozen envelope remaining |
| `IDipaHintsPort` | inference baggage keys |
| `ICheckpointManagerPort` | checkpoint metadata |
| `IExperienceStorePort` | snapshot blob handles |
| `IDashboardPort` | progress / metrics export |
| `IEventSink` / `IMetricsSink` | observability bridges |

## Future integration points

| System | Integration |
|--------|-------------|
| **ARMORA** | Admit + freeze envelope before `create()`; budget slice on each assignment |
| **HAOE** | Adapter implements `IHaoeExecutionPort` → `WorkflowExecutor` / worker pools |
| **Task Graph** | Use swarm `TaskGraph` + `to_haoe_graph` at HAOE boundary |
| **Swarm Context** | `attach_context` / child + merge on fan-out/fan-in |
| **Experience Store** | Persist checkpoint snapshots for AROP replay (Plane 5) |
| **Checkpoint Manager** | Durable restore across process restarts |
| **Agent Registry** | Wire `AgentRegistryService` as `IAgentCatalogPort` |
| **Dashboard / RMF** | Export via `IDashboardPort` + metric bridges |

### Future distributed orchestration

This package is single-process coordination today. A future multi-node design would:

1. Shard workflow executions by `execution_id`
2. Keep Meta Orchestrator as the control-plane reconciler
3. Leave HAOE worker pools + DIPA backends as data-plane
4. Use Experience Store / Checkpoint Manager for cross-node handoff

## Tests

```bash
pytest tests/meta_orchestrator -q
```

## Design principles

- SOLID + constructor DI
- Strong typing (Pydantic v2)
- Async-first coordination loop
- Protocol-only peer boundaries
- Zero global kernel state
