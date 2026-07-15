# Agent Registry

Production **runtime capability catalog** for **NEXUS-ARM**.

Package: `neuroswarm_arm.runtime.swarm.agent_registry`

This is **not** a dictionary of agents, a factory, or a toy plugin loader.
It is the subsystem every planner and scheduler consults to answer:

> **Who can execute this task, under these constraints?**

Think Kubernetes API Server object catalog, Ray worker registry, HashiCorp service discovery, LangGraph agent metadata — applied to ARM-native agentic runtime on GCP Axion.

## Architecture

```
User → ARMORA → HAOE → Task Graph → Agent Registry → Agent Runtime → DIPA
                         (WHAT)         (WHO)
```

| Layer | Role |
|-------|------|
| **Agent / AgentCapability** | Strongly typed capability records (Pydantic) |
| **RegistryStore** | Primary map + secondary indexes |
| **AgentRegistry** | CRUD, lifecycle, lookup, versioning |
| **AgentSelector + scoring** | Deterministic weighted selection |
| **Health / Heartbeat** | Availability, success rate, EMA latency/cost |
| **Cache / Events / Metrics** | Query cache, OTel-ready events, counters |
| **AgentRegistryService** | Facade implementing consumer Protocols |
| **Plugins / Loader** | External agents via import path (no downloads) |

```
TaskGraph / HAOE / ARMORA / DIPA / Governor / Memory / Swarm / Dashboard
        │  (Protocols only — no kernel imports)
        ▼
 AgentRegistryService
        ├── AgentRegistry → RegistryStore
        ├── AgentSelector → scoring
        ├── HeartbeatRecorder
        ├── RegistryCache
        └── PluginLoader / AgentLoader
```

Live chat path is **not** wired yet. Integration surfaces are Protocols in `interfaces.py`.

## Registry model

`Agent` fields cover identity, lifecycle `status`, estimates (latency/cost/tokens/memory/cpu),
supported tools/models/backends/quantizations, feature flags, nested `capabilities`,
`health`, and versioning.

Operations: `register`, `unregister`, `replace`, `update`, `clone`, `freeze`,
`enable`, `disable`, bulk ops, predicate `query`, and lookups by id/name/capability/
model/tool/backend/quantization/tags/priority/health/cost/latency.

## Capability model

`AgentCapability` declares supported tasks/workflows/tools/models/backends/quants/
embeddings/memory/languages/file types, boolean feature flags, context limits,
and preferred_* hints. Indexed via `capability_keys()` (`task:…`, `tool:…`, `flag:…`).

## Selection engine

Hard filters (lifecycle, health floor, required tools/models/backends/quants, budget)
then weighted soft scores:

| Signal | Default weight |
|--------|----------------|
| Capability / task match | 0.25 |
| Tool overlap | 0.15 |
| Model overlap | 0.10 |
| Backend / quant | 0.10 |
| Latency vs budget | 0.10 |
| Cost vs budget | 0.10 |
| Health | 0.10 |
| Priority | 0.05 |
| Confidence | 0.05 |

No ML. Fully deterministic. Weights via `ScoringWeights`.

## Lifecycle

```
CREATED → REGISTERED → LOADED → READY ⇄ BUSY
                              ↘ PAUSED / DISABLED / FAILED
FAILED → RESTARTING → LOADED|READY
* → RETIRED
```

Illegal transitions raise `LifecycleError`. Selector only considers `READY` / `BUSY`.

## Plugin architecture

```python
from neuroswarm_arm.runtime.swarm.agent_registry import (
    PluginLoader, CallablePlugin, build_agent_registry,
)

svc = build_agent_registry(include_builtins=True)
svc.plugins.register(CallablePlugin("mine", lambda: [...agents...]))
svc.load_plugins()
# or: svc.plugins.load_module("my_pkg.agents", attr="plugin")
```

**No dynamic downloads.** Import-path / explicit register only.

## Built-in profiles

Research, Coding, Planning, Reviewer, Memory, Tool, Router, Evaluator,
Summarizer, Coordinator — OKF-aligned ids (`nexus.agents.coding_agent`, …).

```python
from neuroswarm_arm.runtime.swarm.agent_registry import build_agent_registry, SelectionRequest

svc = build_agent_registry()
result = svc.select(SelectionRequest(task="coding", required_tools=["nexus.tools.github"]))
print(result.best.agent_id if result.best else None)
```

## Future: distributed registry

Design target (not implemented): gossip or control-plane sync of Agent records across
Axion nodes, heartbeat aggregation, and affinity-aware selection (NUMA / CXL hints).

## Future: Kubernetes integration

Design target (not implemented): CRD `AgentCapability` + controller that syncs
into this in-process registry; Service-like discovery for remote agent runtimes;
readiness aligned with `LifecycleState.READY`.

## Future integration points

| Consumer | Hook |
|----------|------|
| Task Graph Planner | `resolve_agent_type` before node freeze |
| HAOE | Replace `_agent_profile()` string heuristic |
| ARMORA | `budget_hints` → envelope seed |
| DIPA | `preferred_models` / backend / quant |
| Governor / RTG | `agent_priority` / token preference |
| Memory Runtime | `memory_namespace` / `supported_memory` |
| Swarm Context | `bind_node` + selection events |
| Experience Store / AROP | Subscribe `EventBus` |
| Checkpoint Manager | Filter `checkpoint_support` |

## Public API

```python
from neuroswarm_arm.runtime.swarm.agent_registry import (
    Agent, AgentCapability, AgentRegistry, AgentRegistryService,
    build_agent_registry, register_builtin_profiles,
    AgentSelector, SelectionRequest, SelectionResult,
    LifecycleState, HealthRecord, EventBus,
)
```

## Non-goals

Agent execution, HAOE scheduling, DIPA inference, Memory/Swarm execution,
distributed registry, Kubernetes controllers, RL, prompt evolution.
