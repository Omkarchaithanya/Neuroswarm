# Sub Swarms

Reusable multi-agent **workflow templates** for NEXUS-ARM.

Sub Swarms are **not** autonomous swarm AI, RL, or agent emergence.
They are typed, versioned templates — think Kubernetes Operators, GitHub reusable
workflows, Airflow DAG templates, Temporal child workflows, or LangGraph reusable graphs.

```
User → ARMORA → HAOE → Task Graph → Agent Registry → Swarm Context
     → Workflow Coordination (Meta Orchestrator) → Sub Swarms → DIPA
```

| Layer | Role |
|-------|------|
| Task Graph | Describes execution DAG |
| Agent Registry | Describes capabilities |
| Swarm Context | Carries shared state |
| Meta Orchestrator | Coordinates execution |
| **Sub Swarms** | Reusable workflow templates |

A Sub Swarm **never** schedules, plans, or runs inference.
It only **describes** reusable multi-agent workflows.

---

## Architecture

```
SwarmBuilder / builtins
        │
        ▼
  SwarmTemplate  ──► SubSwarmRegistry
        │                    │
        ▼                    ▼
  SwarmComposer        SwarmSelector (deterministic)
        │
        ▼
ExecutableWorkflowDescription  ──► Meta Orchestrator / HAOE (later)
```

**Ownership:** `neuroswarm_arm.runtime.swarm.sub_swarms`

**Integration style:** Protocol ports only — no concrete HAOE / DIPA / ARMORA imports
from this package (except Task Graph builder used inside builtin factories to attach
frozen graph snapshots).

---

## Template model

`SwarmTemplate` fields include identity (`id`, `name`, `version`, `category`,
`workflow_type`), `task_graph_reference` (id/name + optional frozen snapshot),
agent/tool/model/backend/memory/context/budget requirements, `execution_profile`,
`profile` (resource/budget/latency/cost/memory/model/backend/context), estimates,
parallelism/priority/timeout/retry, metadata/tags/labels, lifecycle `status`,
timestamps.

Methods: `content_hash()`, `clone()`, `evolve()`, `bump_version()`, `freeze()`,
`to_dict()`.

---

## Built-in templates

| Id | Agents |
|----|--------|
| `nexus.swarms.research` | Research, Memory, Reviewer |
| `nexus.swarms.coding` | Planner, Coder, Tester, Reviewer |
| `nexus.swarms.documentation` | Research, Summarizer, Writer, Reviewer |
| `nexus.swarms.tool_execution` | Planner, Tool, Memory, Reviewer |
| `nexus.swarms.analysis` | Planner, Research, Memory, Evaluator |
| `nexus.swarms.planning` | Planner, Research, Reviewer |
| `nexus.swarms.benchmark` | Planner, Executor, Metrics, Reviewer |

```python
from neuroswarm_arm.runtime.swarm.sub_swarms import build_sub_swarm_manager

mgr = build_sub_swarm_manager()  # registers builtins → READY
tpl = mgr.get("nexus.swarms.coding")
desc = mgr.to_executable("nexus.swarms.coding", parameters={"repo": "nexus"})
```

---

## Workflow composition

`SwarmComposer` supports `clone`, `extend`, `override`, `merge`, `parameterize`,
and `to_executable`. Circular composition is rejected via provenance /
`composition_of` checks.

```python
from neuroswarm_arm.runtime.swarm.sub_swarms import SwarmBuilder

swarm = (
    SwarmBuilder()
    .template(id="nexus.swarms.custom", name="custom", workflow_type="coding")
    .agents("nexus.agents.planning_agent", "nexus.agents.coding_agent")
    .context("request", "budget")
    .budget("envelope_id")
    .task_graph(graph_name="custom", snapshot={"nodes": {}})
    .build()
)
```

---

## Profiles & constraints

- **Profiles:** `SwarmProfile` aggregates resource, budget, execution, latency,
  cost, memory, model, backend, context sub-profiles.
- **Constraints:** min/max agents, required capabilities/tools/models, budget /
  memory / latency / CPU / token limits, execution policies.
- **Validation:** missing task graph, missing agents, invalid capabilities,
  missing context/budget, version errors, duplicates, circular composition.

---

## Selection

Deterministic hard filters + weighted scores (`SwarmSelector`). No AI. No RL.

Inputs: workflow type, task type, capabilities, budget, context.
Output: ranked `SwarmSelectionResult`.

---

## Lifecycle

`CREATED → REGISTERED → READY → DEPRECATED | DISABLED → ARCHIVED`

Only `READY` templates are selectable.

---

## Versioning & serialization

- Semver on templates (`bump_semver`, `compare_semver`).
- Schema version + `migrate()` for payloads.
- JSON / YAML via `SwarmSerializer` (`dumps` / `loads`).

---

## Events & metrics

Events: `SwarmRegistered`, `SwarmUpdated`, `SwarmSelected`, `SwarmValidated`,
`SwarmDeprecated`, `SwarmArchived` (OTel-ready attributes under `nexus.sub_swarm.*`).

Metrics (bounded labels only — never `workflow_id` / `request_id`):
template usage, selection frequency, average latency/cost, success rate,
execution count.

---

## Public APIs

```python
from neuroswarm_arm.runtime.swarm.sub_swarms import (
    SwarmTemplate,
    SwarmBuilder,
    SwarmComposer,
    SubSwarmRegistry,
    SubSwarmManager,
    build_sub_swarm_manager,
    SwarmSelector,
    SwarmValidator,
    SwarmSelectionRequest,
    ExecutableWorkflowDescription,
    register_builtin_templates,
)
```

Factory: `build_sub_swarm_manager(register_builtins=True, promote_builtins_to_ready=True)`.

---

## Architectural decisions

1. **Templates only** — no scheduling / inference / planning in this package.
2. **Protocol DI** — peers integrate via ports in `interfaces.py`.
3. **Deterministic selection** — reproducible scoring, stable sort.
4. **Non-breaking** — additive package; swarm root does not re-export (same as
   `agent_registry`); live HAOE chat path unchanged.
5. **Task Graph snapshots** — builtins attach frozen graph JSON; consumers may
   rehydrate later via Task Graph serializer.

---

## Extension points

| Extension | How |
|-----------|-----|
| Custom templates | `registry.register(SwarmTemplate(...))` or `SwarmBuilder` |
| Custom scoring | Pass `ScoringWeights` into `SwarmSelector` / manager |
| Event sinks | `EventBus.subscribe(handler)` |
| Schema evolution | Extend `versioning.migrate` |
| Profiles | Merge via `SwarmProfile.merge` / composer `extend` |

---

## Future integration points

| Peer | Port / hook |
|------|-------------|
| Task Graph | `ITaskGraphTemplatePort` — resolve/attach graph refs |
| Agent Registry | `IAgentRegistryLookupPort` — validate agent ids |
| Swarm Context | `ISwarmContextDefaultsPort` — context defaults/keys |
| Meta Orchestrator | `IMetaOrchestratorTemplatePort.accept_workflow_description` |
| ARMORA | `IArmoraBudgetHintsPort` — cost/token hints |
| HAOE | `IHaoeWorkflowHintsPort` — workflow_type / parallelism |
| DIPA | `IDipaModelHintsPort` — model/backend hints |
| Experience Store | `IExperienceStoreTemplatePort` — selection/usage snapshots |
| Checkpoint Manager | `ICheckpointTemplatePort` — checkpoint metadata |
| Dashboard | `IDashboardSwarmView` — list + metrics |

---

## Future distributed swarms

Out of scope today. Template metadata includes room for distributed labels;
execution remains local to HAOE / Meta Orchestrator when wired. No K8s gossip,
no cross-node formation, no emergent sub-swarm RL.

---

## Non-goals

- RL / emergent behaviour / agent execution
- Scheduling / planning / inference
- DIPA / HAOE scheduler / Mem0 / OKF implementations
- Distributed execution / Kubernetes
