# Swarm Context Operating System

Production shared runtime state for **NEXUS-ARM** — what every agent knows during execution.

Package: `neuroswarm_arm.runtime.swarm.context`

This is **not** a dict, LangChain memory, or ACR prompt assembly. It is the Context OS analogue of a Linux process context / K8s pod spec / Ray runtime context for the swarm plane.

## Architecture

```
User → ARMORA → HAOE → Task Graph → Agent Registry → Swarm Context → Meta Orchestrator → DIPA
                                                      ▲
                                         WHAT EVERY AGENT KNOWS
```

| Layer | Owns |
|-------|------|
| Task Graph | WHAT to execute |
| Agent Registry | WHO can execute |
| **Swarm Context** | Shared operating state |
| ACR (`runtime/acr`) | Prompt assembly / compression (different Context OS) |

### Dual SwarmContext (non-breaking)

| Import | Role |
|--------|------|
| `neuroswarm_arm.runtime.swarm.context.SwarmContext` | **Canonical** Pydantic Context OS |
| `neuroswarm_arm.runtime.swarm.task_graph.SwarmContext` | Legacy dataclass for `GraphExecutor` |

Bridge:

```python
from neuroswarm_arm.runtime.swarm.context.adapters import (
    to_task_graph_context,
    from_task_graph_context,
)
```

## Context model

`SwarmContext` carries:

- Identity: `request_id`, `workflow_id`, `execution_id`, `session_id`, `user_id`, `tenant_id`, `swarm_id`
- Domains: `request`, `budget`, `memory`, `knowledge`, `execution`, `tools`, `metrics`, `trace_context`, `telemetry_context`
- Refs only: Mem0 / OKF / knowledge / tool_registry / agent_registry / task_graph handles
- Lifecycle: checkpoints, history, version, tags, labels, metadata

Ops: `evolve`, `clone`, `content_hash`, `to_dict`, `as_condition_map`, `refresh_metrics`.

## Snapshot model

Immutable `SwarmContextSnapshot` via `create_snapshot` / `restore_snapshot` / `compare_snapshots`.
Snapshots never mutate. Checkpoints wrap snapshot metadata for a future Checkpoint Manager (no I/O here).

## Propagation

| Op | Behavior |
|----|----------|
| `child_context` | DAG fan-out: shared swarm_id, new span, inherited budget used+limits |
| `fork_context` | Speculative path: new swarm_id |
| `branch_context` | Named branch label |
| `subgraph_context` | Scoped pending nodes + subgraph_id baggage |
| `merge_contexts` | Fan-in with `ConflictPolicy` |

## Budget model

Dimensions: cost, tokens, latency, energy, memory, CPU, reasoning.

- Reflects frozen ARMORA `envelope_id` when set
- `apply_usage` / `remaining_*` / `propagate`
- Merge default: `SUM_USAGE` for counters, parent limits

## Memory references

Working / short-term / scratch / temps live in-context.
Mem0, OKF, LTM are **ExternalRef** only — no Mem0/OKF implementation.

## Execution model

Tracks current/completed/pending/failed nodes, retries, timeline, node_results/statuses.
Does not run the graph — `GraphExecutor` / HAOE do.

## Builder

```python
from neuroswarm_arm.runtime.swarm.context import SwarmContextBuilder

ctx = (
    SwarmContextBuilder()
    .request(prompt="...")
    .budget(cost_usd_limit=0.05, frozen=True, envelope_id="...")
    .memory(session_id="...")
    .execution(run_id="...")
    .knowledge(namespaces=["okf/domains/coding"])
    .tools(available_tools=["web_search"])
    .metrics()
    .build()
)
```

## Public APIs

See `__all__` in `__init__.py`. Highlights:

- Core: `SwarmContext`, `SwarmContextBuilder`, `SwarmContextSnapshot`
- Ops: `child_context`, `merge_contexts`, `diff_contexts`, `dumps`/`loads`, `create_checkpoint`
- Validation: `validate_context`, `assert_valid`
- Events: `EventBus`, `ContextCreated`, `SnapshotCreated`, …
- Ports: `IArmoraBudgetPort`, `IHaoeContextPort`, `ITaskGraphContextPort`, …

## Architectural decisions

1. **Pydantic Context OS vs dataclass Task Graph context** — richer validation/versioning without breaking `GraphExecutor`.
2. **Refs not ownership** — Mem0/OKF/registries/graphs referenced by handle only.
3. **Snapshot immutability** — frozen payloads; restore rebuilds a new `SwarmContext`.
4. **ACR boundary** — ACR assembles prompts; Swarm Context carries shared execution state + refs to ACR snapshots if needed.
5. **Interfaces only** — no imports of HAOE/DIPA/ARMORA/Mem0 from this package (adapter to task_graph is the sole peer bridge).

## Extension points

| Port | Consumer |
|------|----------|
| `IArmoraBudgetPort` | Inject frozen envelope remaining |
| `IHaoeContextPort` | CorrelationIds ↔ TraceContext |
| `ITaskGraphContextPort` | `as_condition_map` / attach graph_id |
| `IAgentRegistryPort` | Resolve `current_agent` |
| `IMetaOrchestratorPort` | Future attach/detach |
| `IDipaContextPort` | Inference baggage keys |
| `IGovernorPort` | Admit / pressure |
| `IMemoryRuntimePort` | Session / ref resolve |
| `IExperienceStorePort` | Persist snapshot handle |
| `ICheckpointManagerPort` | Durable checkpoint I/O |
| `IDashboardPort` | Metrics export |

## Future distributed context

Schema versioning (`CONTEXT_SCHEMA_VERSION` + `migrate`) and snapshot/content hashes are designed for cross-node handoff. No distributed runtime in this package.

## Tests

```bash
pytest tests/context -q
```

## Non-goals

No Mem0, OKF, Meta Orchestrator, HAOE/DIPA/agent execution, distributed runtime, RL, or tool execution.
