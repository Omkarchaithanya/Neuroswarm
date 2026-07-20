# Metrics Catalogue

## Cardinality rule

Never use `request_id`, `trace_id`, `span_id`, `execution_id`, `conversation_id`, or `envelope_id` as Prometheus labels. Those belong on spans/logs/events only.

Allowed labels: `tenant`, `agent`, `workflow`, `tier`, `backend`, `model`, `quant`, `outcome`, `exporter`, `pool`, `numa`, `dim`, `hardness`, `action`, `result`, `scope`, `planner_id`, `model_tier`, `subsystem`.

## ROF health

| Series | Type | Description |
|--------|------|-------------|
| `rof_spans_exported_total` | counter | Spans exported |
| `rof_spans_dropped_total` | counter | Drops (queue/sampling) |
| `rof_export_failures_total` | counter | Exporter failures |
| `rof_export_latency_seconds` | gauge | Last batch latency |
| `rof_events_emitted_total` | counter | Events emitted |
| `rof_logs_emitted_total` | counter | JSON logs emitted |
| `rof_metric_label_drops_total` | counter | Forbidden labels dropped |

## Nexus runtime

| Series | Type |
|--------|------|
| `nexus_requests_total` | counter |
| `nexus_request_latency_seconds` | histogram |
| `nexus_planner_duration_seconds` | histogram |
| `nexus_planner_prediction_error` | gauge |
| `nexus_routing_duration_seconds` | histogram |
| `nexus_backend_selected_total` | counter |
| `nexus_inference_duration_seconds` | histogram |
| `nexus_prompt_tokens` | counter |
| `nexus_completion_tokens` | counter |
| `nexus_reasoning_tokens` | counter |
| `nexus_streaming_ttft_seconds` | histogram |
| `nexus_streaming_duration_seconds` | histogram |
| `nexus_queue_wait_seconds` | histogram |
| `nexus_cpu_seconds` | gauge |
| `nexus_memory_bytes` | gauge |
| `nexus_peak_memory_bytes` | gauge |
| `nexus_energy_estimate` | gauge |
| `nexus_cost_estimate` | gauge |

## Preserved subsystem ABI (bridges)

| Prefix | Owner |
|--------|-------|
| `budget_*` | ARMORA Budget |
| `runtime_*` | ARMORA RCIS |
| `neuroswarm_*` / `router_*` / `rtg_*` | MetricsStore |
| `haoe_*` / `dipa_*` / `maks_*` / `kv_*` / `ascr_*` | Peer sources |

ASCR Grafana: dashboard **ASCR / ArmCascade Overview** (`ascr-overview`) panels `ascr_acceptance_rate`, `ascr_speculation_gain`, `ascr_quality_cascade_total`, `dipa_cascade_hit_rate`. Speculation gain is forced to **0** in `text_agree` / quality-cascade modes (no logits).

