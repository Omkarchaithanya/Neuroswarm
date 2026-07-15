# Task Graph Subsystem

Production DAG engine for **NEXUS-ARM** — the canonical workflow representation every request becomes before HAOE executes it.

Package: `neuroswarm_arm.runtime.swarm.task_graph`

This is **not** Airflow, LangGraph, Prefect, or a toy workflow toy. It is the internal plan object for the agent runtime kernel.

## Architecture

```
User Request
    → WorkflowPlanner (templates)
    → TaskGraph (immutable definition)
    → GraphExecutor / HAOE WorkflowExecutor
    → Handlers (DIPA, KV, router, …)
```

| Layer | Role |
|-------|------|
| **Definition** | `TaskGraph` / `TaskNode` / `TaskEdge` — frozen after `build()` / `freeze()` |
| **Analysis** | `DAGAnalyzer` — topo, layers, barriers, critical path, components |
| **Validation** | `GraphValidator` → human-readable `ValidationReport` |
| **Execution state** | `ExecutionState` — mutable statuses, results, metrics |
| **Executor** | `GraphExecutor` — async lifecycle only (no agent/DIPA logic) |
| **HAOE bridge** | `adapters.haoe.to_haoe_graph` / `from_haoe_graph` |

Live chat path still uses HAOE’s thin `TaskGraph` today. Swarm is the rich representation; adapters keep contracts non-breaking.

## Data model

- **TaskNode** — id, name, agent_type, node_type, priority, timeout, retry_policy, condition, budget, resource estimates, tools/models, checkpoint, handler_key, …
- **TaskEdge** — HARD / SOFT / CONDITIONAL / DATA / CONTROL / PRIORITY + label/condition/metadata
- **TaskGraph** — nodes, edges, subgraphs, timeout_policy, versioning, content hash

Immutable definition vs mutable `ExecutionState` / `NodeRuntimeState`.

## Execution model

States: `PENDING → QUEUED → READY → RUNNING → {SUCCEEDED|FAILED|CANCELLED|SKIPPED|TIMED_OUT|RETRYING|CHECKPOINTED}`

- Conditions skip nodes/edges
- Retry: constant / linear / exponential + jitter
- Cancel: node / subtree / downstream / graph (graceful | forced)
- Timeouts: per-node, subgraph policy, workflow
- Layers: Kahn layering → parallel-ready sets + join barriers

Handlers inject via `INodeHandler` — executor never imports DIPA/KV/ARMORA.

## Examples

```python
from neuroswarm_arm.runtime.swarm.task_graph import (
    TaskGraphBuilder,
    WorkflowPlanner,
    GraphExecutor,
    Always,
)

graph = (
    TaskGraphBuilder(name="demo")
    .task("research", estimated_latency=10)
    .parallel("planning", "memory")
    .aggregate("join")
    .retry(max_attempts=3)
    .timeout(5.0)
    .task("response")
    .build()
)

planner = WorkflowPlanner()
chat = planner.plan_chat()
multi = planner.plan_multi_agent()

async def handle(node_id, ctx):
    return {"ok": True, "node": node_id}

result = await GraphExecutor().run(graph, {"research": handle, "planning": handle, ...})
```

```python
from neuroswarm_arm.runtime.swarm.task_graph.adapters import to_haoe_graph, from_haoe_graph

haoe_graph = to_haoe_graph(graph)
roundtrip = from_haoe_graph(haoe_graph)
```

## Extension points

| Hook | Use |
|------|-----|
| `INodeHandler` | HAOE injects chat/cascade/KV handlers |
| `ICondition` / `register_condition` | ARMORA budget / confidence gates |
| `EventBus` + `to_otel_attributes()` | ROF / OpenTelemetry |
| `IMetricsSink` / `GraphMetrics` | RMF bridge (no high-card labels) |
| `GraphSerializer` + schema migrate | Experience Store / Checkpoint Manager |
| `subgraphs` / `extract_subgraph` | Hierarchical plans / distributed shards later |

## Future integration

- **HAOE** — planner builds swarm graph → `to_haoe_graph` → existing `WorkflowExecutor` (phase 2)
- **ARMORA** — `BudgetContext` + condition thresholds before tool/retry/cascade
- **DIPA** — inference nodes stay handler-bound; never import backends here
- **Experience Store** — persist definition hash + metrics snapshots via serializer
- **Checkpoint Manager** — `checkpoint_id` + Checkpoint/Restore events

## Non-goals

No agent execution, HAOE scheduling/pools, DIPA, RL, K8s, or distributed runtime in this package.
