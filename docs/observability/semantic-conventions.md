# Semantic Conventions

## Span names

Format: `nexus.<subsystem>.<operation>`

| Constant | Name |
|----------|------|
| REQUEST | `nexus.armora.request` |
| ADMISSION | `nexus.armora.admission` |
| POLICY | `nexus.armora.policy` |
| BUDGET | `nexus.armora.budget` |
| PLANNER | `nexus.dipa.planner` |
| ROUTING | `nexus.dipa.routing` |
| HAOE_WORKFLOW | `nexus.haoe.workflow` |
| HAOE_TASK | `nexus.haoe.task` |
| DIPA_INFER | `nexus.dipa.infer` |
| BACKEND | `nexus.dipa.backend` |
| STREAMING | `nexus.dipa.streaming` |
| QUANT | `nexus.aqr.quant` |
| WARM | `nexus.awpp.warm` |
| KV | `nexus.maks.kv` |
| COST | `nexus.armora.rcis` |
| EXPORT | `nexus.rof.export` |
| PERFORMIX | `nexus.performix.sample` |

## Attributes / baggage

| Key | Meaning |
|-----|---------|
| `nexus.trace_id` | Trace id |
| `nexus.span_id` | Span id |
| `nexus.request_id` | Request id |
| `nexus.execution_id` | Execution id |
| `nexus.workflow_id` | Workflow id |
| `nexus.agent_id` | Agent id |
| `nexus.envelope_id` | Budget envelope id |
| `nexus.backend_id` | Backend |
| `nexus.model_id` | Model |
| `nexus.quantization` | Quant |
| `nexus.numa_node` | NUMA |
| `nexus.cost_estimate` | Cost |
| `nexus.budget_remaining` | Remaining budget |
| `nexus.force_sample` | Force sampler keep |
| `nexus.outcome` | ok/error/… |
| `nexus.error` | Error message |

## GenAI + MCP (router / execute)

When `NSA_ROUTER_OTEL=1`, router and MCP execute spans also emit (Development semconv — dual keys for upgrade safety):

| Key | Meaning |
|-----|---------|
| `gen_ai.system` | Provider id (`neuroswarm`) — legacy |
| `gen_ai.provider.name` | Provider id (`neuroswarm`) — newer |
| `gen_ai.operation.name` | `route` / `embed` / `mcp_tools_call` |
| `mcp.method.name` | e.g. `tools/call` |
| `mcp.session.id` | `{server_id}:{tool}` |
| `mcp.protocol.version` | MCP protocol (`2025-11-25`) |

Existing `nexus.*` attributes remain for the Prometheus bridge.

## Events

`AdmissionStarted`, `AdmissionFinished`, `PlannerStarted`, `PlannerCompleted`, `RoutingStarted`, `RoutingCompleted`, `InferenceStarted`, `InferenceFinished`, `StreamingStarted`, `StreamingFinished`, `BudgetExceeded`, `BackendFailure`, `RetryStarted`, `RetryFinished`, `ProfilerStarted`, `ProfilerFinished`, `CostReportGenerated`, `PlannerLearned`, plus custom via `register_event_type`.
