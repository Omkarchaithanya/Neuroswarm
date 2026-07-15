"""Canonical nexus_* metric catalogue for all 12 RMF domains."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..schemas import (
    DEFAULT_JOULE_BUCKETS,
    DEFAULT_LATENCY_BUCKETS,
    MetricDef,
    MetricDomain,
    MetricType,
)

if TYPE_CHECKING:
    from ..registry import MetricRegistry

L_STATUS = ("status",)
L_BACKEND = ("backend", "status")
L_ROUTE = ("backend", "model", "model_tier", "quantization", "status")
L_WORKER = ("worker", "thread_pool", "numa_node")
L_REQ = ("request_type", "streaming", "reasoning", "status", "agent_type")
L_PLAN = ("planner", "status")
L_DIM = ("dim",)


def _c(name: str, help_text: str, domain: MetricDomain, labels: tuple[str, ...] = (), aliases: tuple[str, ...] = ()) -> MetricDef:
    return MetricDef(
        name=name,
        metric_type=MetricType.COUNTER,
        help=help_text,
        domain=domain,
        label_keys=labels,
        aliases=aliases,
    )


def _g(name: str, help_text: str, domain: MetricDomain, labels: tuple[str, ...] = (), aliases: tuple[str, ...] = ()) -> MetricDef:
    return MetricDef(
        name=name,
        metric_type=MetricType.GAUGE,
        help=help_text,
        domain=domain,
        label_keys=labels,
        aliases=aliases,
    )


def _h(
    name: str,
    help_text: str,
    domain: MetricDomain,
    labels: tuple[str, ...] = (),
    buckets: tuple[float, ...] = DEFAULT_LATENCY_BUCKETS,
    aliases: tuple[str, ...] = (),
    native: bool = False,
) -> MetricDef:
    return MetricDef(
        name=name,
        metric_type=MetricType.NATIVE_HISTOGRAM if native else MetricType.HISTOGRAM,
        help=help_text,
        domain=domain,
        label_keys=labels,
        buckets=buckets,
        aliases=aliases,
        native_histogram=native,
    )


DOMAIN_METRICS: tuple[MetricDef, ...] = (
    # RMF internal
    _c("nexus_rmf_buffer_drops_total", "Metric buffer drops under backpressure", MetricDomain.RMF),
    _c("nexus_rmf_label_drops_total", "Forbidden or unknown labels dropped", MetricDomain.RMF),
    _c("nexus_rmf_cardinality_rejects_total", "Series rejected by cardinality cap", MetricDomain.RMF),
    _g("nexus_rmf_registry_series", "Current registered series count", MetricDomain.RMF),
    MetricDef(
        name="nexus_rmf_build_info",
        metric_type=MetricType.INFO,
        help="RMF build metadata",
        domain=MetricDomain.RMF,
        label_keys=("version", "framework"),
    ),
    # 1 Request
    _c("nexus_request_total", "Total runtime requests", MetricDomain.REQUEST, L_REQ, ("neuroswarm_requests_total", "nexus_requests_total")),
    _g("nexus_request_active", "In-flight requests", MetricDomain.REQUEST, L_REQ),
    _c("nexus_request_failed_total", "Failed requests", MetricDomain.REQUEST, L_REQ),
    _c("nexus_request_cancelled_total", "Cancelled requests", MetricDomain.REQUEST, L_REQ),
    _c("nexus_request_streaming_total", "Streaming requests", MetricDomain.REQUEST, L_REQ),
    _c("nexus_request_completed_total", "Completed requests", MetricDomain.REQUEST, L_REQ),
    _h("nexus_request_duration_seconds", "End-to-end request latency", MetricDomain.REQUEST, L_REQ, aliases=("nexus_request_latency_seconds",)),
    # 2 Admission
    _h("nexus_admission_duration_seconds", "Admission decision latency", MetricDomain.ADMISSION, L_STATUS),
    _c("nexus_admission_failures_total", "Admission failures", MetricDomain.ADMISSION, L_STATUS),
    _g("nexus_admission_queue", "Admission queue depth", MetricDomain.ADMISSION),
    # 3 Planner
    _h("nexus_planner_latency_seconds", "Planner latency", MetricDomain.PLANNER, L_PLAN, aliases=("nexus_planner_duration_seconds",)),
    _g("nexus_planner_prediction_error", "Planner prediction absolute error", MetricDomain.PLANNER, L_PLAN),
    _c("nexus_planner_success_total", "Successful planner decisions", MetricDomain.PLANNER, L_PLAN),
    _c("nexus_planner_budget_violations_total", "Planner budget violations", MetricDomain.PLANNER, L_PLAN),
    _c("nexus_planner_route_changes_total", "Planner route changes", MetricDomain.PLANNER, L_PLAN),
    _c("nexus_planner_decision_count_total", "Planner decisions", MetricDomain.PLANNER, L_PLAN),
    # 4 Routing
    _c("nexus_routing_model_tier_usage_total", "Model tier usage", MetricDomain.ROUTING, ("model_tier", "status")),
    _c("nexus_routing_backend_usage_total", "Backend usage", MetricDomain.ROUTING, L_BACKEND, ("nexus_backend_selected_total",)),
    _c("nexus_routing_quantization_usage_total", "Quantization usage", MetricDomain.ROUTING, ("quantization", "status")),
    _c("nexus_routing_worker_usage_total", "Worker usage", MetricDomain.ROUTING, ("worker", "status")),
    _h("nexus_routing_latency_seconds", "Routing latency", MetricDomain.ROUTING, L_ROUTE, aliases=("nexus_routing_duration_seconds",)),
    _c("nexus_routing_failures_total", "Routing failures", MetricDomain.ROUTING, L_ROUTE),
    # 5 HAOE
    _h("nexus_haoe_scheduler_latency_seconds", "HAOE scheduler latency", MetricDomain.HAOE, L_WORKER),
    _g("nexus_haoe_queue_depth", "HAOE queue depth", MetricDomain.HAOE, ("pool",), ("haoe_queue_depth",)),
    _g("nexus_haoe_worker_utilization", "Worker utilization 0..1", MetricDomain.HAOE, L_WORKER, ("haoe_worker_utilization",)),
    _g("nexus_haoe_thread_utilization", "Thread utilization 0..1", MetricDomain.HAOE, L_WORKER),
    _c("nexus_haoe_cpu_affinity_changes_total", "CPU affinity changes", MetricDomain.HAOE, L_WORKER),
    _g("nexus_haoe_numa_distribution", "Tasks per NUMA node", MetricDomain.HAOE, ("numa_node",)),
    _c("nexus_haoe_steal_total", "Work-steal operations", MetricDomain.HAOE, aliases=("haoe_steal_total",)),
    # 6 DIPA
    _h("nexus_dipa_prefill_latency_seconds", "Prefill latency", MetricDomain.DIPA, L_ROUTE),
    _h("nexus_dipa_decode_latency_seconds", "Decode latency", MetricDomain.DIPA, L_ROUTE),
    _h("nexus_dipa_stream_latency_seconds", "Stream latency", MetricDomain.DIPA, L_ROUTE),
    _h("nexus_dipa_backend_latency_seconds", "Backend latency", MetricDomain.DIPA, L_ROUTE, aliases=("nexus_inference_duration_seconds",)),
    _c("nexus_dipa_speculative_acceptance_total", "Speculative acceptances", MetricDomain.DIPA, L_ROUTE),
    _c("nexus_dipa_speculative_rejection_total", "Speculative rejections", MetricDomain.DIPA, L_ROUTE),
    _h("nexus_dipa_ttft_seconds", "Time to first token", MetricDomain.DIPA, L_ROUTE, aliases=("nexus_streaming_ttft_seconds",)),
    # 7 Budget
    _g("nexus_budget_remaining", "Budget remaining", MetricDomain.BUDGET, L_DIM, ("budget_remaining",)),
    _g("nexus_budget_consumed", "Budget consumed", MetricDomain.BUDGET, L_DIM),
    _c("nexus_budget_violation_total", "Budget violations", MetricDomain.BUDGET, L_DIM, ("budget_violation_total",)),
    _g("nexus_budget_cost_remaining", "Cost budget remaining USD", MetricDomain.BUDGET),
    _g("nexus_budget_token_remaining", "Token budget remaining", MetricDomain.BUDGET),
    _g("nexus_budget_memory_remaining", "Memory budget remaining bytes", MetricDomain.BUDGET),
    # 8 Runtime cost
    _g("nexus_cost_per_token", "Cost per token USD", MetricDomain.RUNTIME_COST, L_ROUTE, ("runtime_cost_per_token",)),
    _g("nexus_cost_per_request", "Cost per request USD", MetricDomain.RUNTIME_COST, L_ROUTE),
    _g("nexus_cpu_seconds", "CPU seconds", MetricDomain.RUNTIME_COST, aliases=("runtime_cpu_seconds",)),
    _g("nexus_tokens_per_second", "Tokens per second", MetricDomain.RUNTIME_COST, L_ROUTE),
    _g("nexus_tokens_per_watt", "Tokens per watt", MetricDomain.RUNTIME_COST, L_ROUTE, ("runtime_tokens_per_watt",)),
    _g("nexus_tokens_per_dollar", "Tokens per dollar", MetricDomain.RUNTIME_COST, L_ROUTE, ("runtime_tokens_per_dollar",)),
    _g("nexus_planner_cost_error", "Planner cost prediction error", MetricDomain.RUNTIME_COST, L_PLAN, ("runtime_planner_prediction_error",)),
    _c("nexus_runtime_cost_total", "Cumulative runtime cost USD", MetricDomain.RUNTIME_COST, L_ROUTE, ("runtime_cost_total",)),
    # 9 Memory
    _g("nexus_memory_rss_bytes", "RSS memory bytes", MetricDomain.MEMORY, aliases=("nexus_memory_bytes",)),
    _g("nexus_memory_peak_bytes", "Peak memory bytes", MetricDomain.MEMORY, aliases=("nexus_peak_memory_bytes",)),
    _g("nexus_kv_cache_bytes", "KV cache bytes", MetricDomain.MEMORY),
    _c("nexus_kv_cache_hits_total", "KV cache hits", MetricDomain.MEMORY, ("tier",)),
    _c("nexus_kv_cache_misses_total", "KV cache misses", MetricDomain.MEMORY, ("tier",)),
    _g("nexus_kv_cache_reuse", "KV cache reuse ratio", MetricDomain.MEMORY, aliases=("runtime_kv_reuse",)),
    _c("nexus_kv_cache_evictions_total", "KV cache evictions", MetricDomain.MEMORY, ("tier",)),
    _c("nexus_mem0_hits_total", "Mem0 hits", MetricDomain.MEMORY),
    _c("nexus_okf_loads_total", "OKF document loads", MetricDomain.MEMORY),
    # 10 Hardware
    _g("nexus_hw_cpu_usage", "CPU usage ratio 0..1", MetricDomain.HARDWARE, ("numa_node",)),
    _g("nexus_hw_cpu_frequency_hz", "CPU frequency Hz", MetricDomain.HARDWARE, ("numa_node",)),
    _g("nexus_hw_thread_count", "Thread count", MetricDomain.HARDWARE),
    _g("nexus_hw_memory_usage_bytes", "Process memory usage bytes", MetricDomain.HARDWARE),
    _g("nexus_hw_cache_utilization", "Cache utilization estimate 0..1", MetricDomain.HARDWARE),
    _c("nexus_hw_context_switches_total", "Context switches", MetricDomain.HARDWARE),
    _g("nexus_hw_numa_node_usage", "NUMA node memory usage bytes", MetricDomain.HARDWARE, ("numa_node",)),
    _g("nexus_hw_sve2_utilization", "SVE2 utilization estimate 0..1", MetricDomain.HARDWARE),
    # 11 Performix
    _g("nexus_performix_available", "1 if Performix available else 0", MetricDomain.PERFORMIX),
    _g("nexus_performix_cycles", "CPU cycles", MetricDomain.PERFORMIX),
    _g("nexus_performix_instructions", "Retired instructions", MetricDomain.PERFORMIX),
    _g("nexus_performix_ipc", "Instructions per cycle", MetricDomain.PERFORMIX),
    _g("nexus_performix_cache_misses", "Cache misses", MetricDomain.PERFORMIX),
    _g("nexus_performix_branch_misses", "Branch misses", MetricDomain.PERFORMIX),
    _g("nexus_performix_pmu_events", "Generic PMU event count", MetricDomain.PERFORMIX, ("event",)),
    # 12 Energy
    _g("nexus_energy_estimated_joules", "Estimated joules", MetricDomain.ENERGY, aliases=("nexus_energy_estimate", "runtime_energy_estimate")),
    _g("nexus_energy_estimated_power_watts", "Estimated power watts", MetricDomain.ENERGY),
    _h(
        "nexus_energy_per_token_joules",
        "Energy per token joules",
        MetricDomain.ENERGY,
        L_ROUTE,
        DEFAULT_JOULE_BUCKETS,
    ),
    _h(
        "nexus_energy_per_request_joules",
        "Energy per request joules",
        MetricDomain.ENERGY,
        L_ROUTE,
        DEFAULT_JOULE_BUCKETS,
    ),
    # Legacy gateway aliases registered as first-class for dual-write
    _c("neuroswarm_cascade_tier_1_total", "Tier 1 cascade requests", MetricDomain.LEGACY),
    _c("neuroswarm_cascade_tier_2_total", "Tier 2 cascade requests", MetricDomain.LEGACY),
    _c("neuroswarm_cascade_tier_3_total", "Tier 3 cascade requests", MetricDomain.LEGACY),
    _g("neuroswarm_last_request_latency_ms", "Last request latency ms", MetricDomain.LEGACY),
    _g("neuroswarm_last_tier_used", "Last cascade tier", MetricDomain.LEGACY),
    _g("neuroswarm_last_thinking_token_cap", "Last thinking token cap", MetricDomain.LEGACY),
    _g("neuroswarm_last_tool_schema_count", "Last tool schema count", MetricDomain.LEGACY),
    _c("rtg_admits_total", "RTG admits", MetricDomain.LEGACY),
    _c("rtg_decisions_total", "RTG decisions", MetricDomain.LEGACY),
    _c("rtg_early_exit_total", "RTG early exits", MetricDomain.LEGACY),
    _c("rtg_completions_total", "RTG completions", MetricDomain.LEGACY),
    _g("rtg_budget_remaining", "RTG budget remaining", MetricDomain.LEGACY),
    _g("rtg_thinking_tokens", "RTG thinking tokens", MetricDomain.LEGACY),
    _g("rtg_last_initial_budget", "RTG initial budget", MetricDomain.LEGACY),
    _g("rtg_last_confidence", "RTG confidence", MetricDomain.LEGACY),
    _c("router_requests_total", "Router requests", MetricDomain.LEGACY),
    _g("router_routing_latency_ms", "Router latency ms", MetricDomain.LEGACY),
    _g("router_embedding_latency_ms", "Embedding latency ms", MetricDomain.LEGACY),
    _g("router_ann_latency_ms", "ANN latency ms", MetricDomain.LEGACY),
    _g("router_rerank_latency_ms", "Rerank latency ms", MetricDomain.LEGACY),
    _g("router_cache_hit_ratio", "Router cache hit ratio", MetricDomain.LEGACY),
    _g("router_avg_confidence", "Router avg confidence", MetricDomain.LEGACY),
    _g("router_avg_token_reduction", "Router avg token reduction", MetricDomain.LEGACY),
    _g("router_index_size", "Router index size", MetricDomain.LEGACY),
    _g("router_tools_registered", "Tools registered", MetricDomain.LEGACY),
)


def register_all_domains(registry: MetricRegistry) -> None:
    for definition in DOMAIN_METRICS:
        registry.register(definition)
    registry.info(
        "nexus_rmf_build_info",
        {"version": "1.0.0", "framework": "rmf"},
    )
