# Metric Catalogue

Source of truth: `neuroswarm_arm/metrics/domains/catalogue.py` (`DOMAIN_METRICS`).

## 1. Request

| Metric | Type | Labels |
|--------|------|--------|
| `nexus_request_total` | counter | request_type, streaming, reasoning, status, agent_type |
| `nexus_request_active` | gauge | same |
| `nexus_request_failed_total` | counter | same |
| `nexus_request_cancelled_total` | counter | same |
| `nexus_request_streaming_total` | counter | same |
| `nexus_request_completed_total` | counter | same |
| `nexus_request_duration_seconds` | histogram | same |

## 2. Admission

| Metric | Type |
|--------|------|
| `nexus_admission_duration_seconds` | histogram |
| `nexus_admission_failures_total` | counter |
| `nexus_admission_queue` | gauge |

## 3. Planner

| Metric | Type |
|--------|------|
| `nexus_planner_latency_seconds` | histogram |
| `nexus_planner_prediction_error` | gauge |
| `nexus_planner_success_total` | counter |
| `nexus_planner_budget_violations_total` | counter |
| `nexus_planner_route_changes_total` | counter |
| `nexus_planner_decision_count_total` | counter |

## 4. Routing

| Metric | Type |
|--------|------|
| `nexus_routing_model_tier_usage_total` | counter |
| `nexus_routing_backend_usage_total` | counter |
| `nexus_routing_quantization_usage_total` | counter |
| `nexus_routing_worker_usage_total` | counter |
| `nexus_routing_latency_seconds` | histogram |
| `nexus_routing_failures_total` | counter |

## 5. HAOE

| Metric | Type |
|--------|------|
| `nexus_haoe_scheduler_latency_seconds` | histogram |
| `nexus_haoe_queue_depth` | gauge |
| `nexus_haoe_worker_utilization` | gauge |
| `nexus_haoe_thread_utilization` | gauge |
| `nexus_haoe_cpu_affinity_changes_total` | counter |
| `nexus_haoe_numa_distribution` | gauge |
| `nexus_haoe_steal_total` | counter |

## 6. DIPA

| Metric | Type |
|--------|------|
| `nexus_dipa_prefill_latency_seconds` | histogram |
| `nexus_dipa_decode_latency_seconds` | histogram |
| `nexus_dipa_stream_latency_seconds` | histogram |
| `nexus_dipa_backend_latency_seconds` | histogram |
| `nexus_dipa_speculative_acceptance_total` | counter |
| `nexus_dipa_speculative_rejection_total` | counter |
| `nexus_dipa_ttft_seconds` | histogram |

## 7–12. Budget, Cost, Memory, Hardware, Performix, Energy

See catalogue module for full list including:

- `nexus_budget_remaining`, `nexus_budget_violation_total`, …
- `nexus_cost_per_token`, `nexus_tokens_per_dollar`, …
- `nexus_kv_cache_*`, `nexus_memory_rss_bytes`, …
- `nexus_hw_cpu_usage`, `nexus_hw_sve2_utilization`, …
- `nexus_performix_*` (zeros when Performix unavailable)
- `nexus_energy_estimated_joules`, `nexus_energy_per_token_joules`, …
