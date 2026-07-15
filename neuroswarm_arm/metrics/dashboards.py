"""Grafana dashboard JSON builders for RMF domains."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _panel(panel_id: int, title: str, expr: str, y: int, x: int = 0, w: int = 12, h: int = 8) -> dict[str, Any]:
    return {
        "id": panel_id,
        "type": "timeseries",
        "title": title,
        "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "targets": [{"refId": "A", "expr": expr, "legendFormat": "{{instance}}"}],
        "fieldConfig": {"defaults": {}, "overrides": []},
    }


def _dashboard(uid: str, title: str, panels: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "uid": uid,
        "title": title,
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 1,
        "refresh": "10s",
        "tags": ["nexus", "rmf"],
        "panels": panels,
        "templating": {"list": []},
        "annotations": {"list": []},
        "editable": True,
    }


def default_dashboards() -> dict[str, dict[str, Any]]:
    return {
        "rmf-runtime-overview": _dashboard(
            "rmf-runtime-overview",
            "RMF Runtime Overview",
            [
                _panel(1, "Request rate", "sum(rate(nexus_request_total[1m]))", 0),
                _panel(2, "P95 latency", "nexus:request_duration_seconds:p95_5m", 0, x=12),
                _panel(3, "Active requests", "nexus_request_active", 8),
                _panel(4, "Error rate", "sum(rate(nexus_request_failed_total[1m]))", 8, x=12),
            ],
        ),
        "rmf-planner": _dashboard(
            "rmf-planner",
            "RMF Planner Dashboard",
            [
                _panel(1, "Planner latency", "nexus:planner_latency_seconds:avg5m", 0),
                _panel(2, "Prediction error", "avg(nexus_planner_prediction_error)", 0, x=12),
                _panel(3, "Decisions", "sum(rate(nexus_planner_decision_count_total[1m]))", 8),
                _panel(4, "Budget violations", "sum(rate(nexus_planner_budget_violations_total[1m]))", 8, x=12),
            ],
        ),
        "rmf-routing": _dashboard(
            "rmf-routing",
            "RMF Routing Dashboard",
            [
                _panel(1, "Backend usage", "sum by (backend) (rate(nexus_routing_backend_usage_total[1m]))", 0),
                _panel(2, "Model tier", "sum by (model_tier) (rate(nexus_routing_model_tier_usage_total[1m]))", 0, x=12),
                _panel(3, "Quantization", "sum by (quantization) (rate(nexus_routing_quantization_usage_total[1m]))", 8),
                _panel(4, "Routing failures", "sum(rate(nexus_routing_failures_total[1m]))", 8, x=12),
            ],
        ),
        "rmf-budget": _dashboard(
            "rmf-budget",
            "RMF Budget Dashboard",
            [
                _panel(1, "Budget remaining", "nexus_budget_remaining", 0),
                _panel(2, "Violations", "sum(rate(nexus_budget_violation_total[1m]))", 0, x=12),
                _panel(3, "Token remaining", "nexus_budget_token_remaining", 8),
                _panel(4, "Cost remaining", "nexus_budget_cost_remaining", 8, x=12),
            ],
        ),
        "rmf-inference": _dashboard(
            "rmf-inference",
            "RMF Inference Dashboard",
            [
                _panel(1, "Prefill P95", "nexus:dipa_prefill_latency_seconds:p95_5m", 0),
                _panel(2, "Decode latency", "histogram_quantile(0.95, sum(rate(nexus_dipa_decode_latency_seconds_bucket[5m])) by (le))", 0, x=12),
                _panel(3, "TTFT", "histogram_quantile(0.95, sum(rate(nexus_dipa_ttft_seconds_bucket[5m])) by (le))", 8),
                _panel(4, "Spec accept/reject", "sum(rate(nexus_dipa_speculative_acceptance_total[1m]))", 8, x=12),
            ],
        ),
        "rmf-haoe": _dashboard(
            "rmf-haoe",
            "RMF HAOE Dashboard",
            [
                _panel(1, "Queue depth", "nexus_haoe_queue_depth", 0),
                _panel(2, "Worker util", "avg(nexus_haoe_worker_utilization)", 0, x=12),
                _panel(3, "Steals", "sum(rate(nexus_haoe_steal_total[1m]))", 8),
                _panel(4, "NUMA distribution", "nexus_haoe_numa_distribution", 8, x=12),
            ],
        ),
        "rmf-dipa": _dashboard(
            "rmf-dipa",
            "RMF DIPA Dashboard",
            [
                _panel(1, "Backend latency", "histogram_quantile(0.95, sum(rate(nexus_dipa_backend_latency_seconds_bucket[5m])) by (le))", 0),
                _panel(2, "Stream latency", "histogram_quantile(0.95, sum(rate(nexus_dipa_stream_latency_seconds_bucket[5m])) by (le))", 0, x=12),
                _panel(3, "Spec rejection", "sum(rate(nexus_dipa_speculative_rejection_total[1m]))", 8),
            ],
        ),
        "rmf-memory": _dashboard(
            "rmf-memory",
            "RMF Memory Dashboard",
            [
                _panel(1, "RSS", "nexus_memory_rss_bytes", 0),
                _panel(2, "Peak", "nexus_memory_peak_bytes", 0, x=12),
                _panel(3, "Mem0 hits", "sum(rate(nexus_mem0_hits_total[1m]))", 8),
                _panel(4, "OKF loads", "sum(rate(nexus_okf_loads_total[1m]))", 8, x=12),
            ],
        ),
        "rmf-kv": _dashboard(
            "rmf-kv",
            "RMF KV Dashboard",
            [
                _panel(1, "KV bytes", "nexus_kv_cache_bytes", 0),
                _panel(2, "Reuse", "nexus_kv_cache_reuse", 0, x=12),
                _panel(3, "Hits", "sum(rate(nexus_kv_cache_hits_total[1m]))", 8),
                _panel(4, "Evictions", "sum(rate(nexus_kv_cache_evictions_total[1m]))", 8, x=12),
            ],
        ),
        "rmf-energy": _dashboard(
            "rmf-energy",
            "RMF Energy Dashboard",
            [
                _panel(1, "Joules", "nexus_energy_estimated_joules", 0),
                _panel(2, "Power", "nexus_energy_estimated_power_watts", 0, x=12),
                _panel(3, "Energy/token", "histogram_quantile(0.95, sum(rate(nexus_energy_per_token_joules_bucket[5m])) by (le))", 8),
            ],
        ),
        "rmf-cost": _dashboard(
            "rmf-cost",
            "RMF Cost Dashboard",
            [
                _panel(1, "Cost/request", "nexus:cost_per_request:avg5m", 0),
                _panel(2, "Cost/token", "avg(nexus_cost_per_token)", 0, x=12),
                _panel(3, "Tokens/$", "avg(nexus_tokens_per_dollar)", 8),
                _panel(4, "Tokens/W", "avg(nexus_tokens_per_watt)", 8, x=12),
            ],
        ),
        "rmf-arm-hardware": _dashboard(
            "rmf-arm-hardware",
            "RMF ARM Hardware Dashboard",
            [
                _panel(1, "CPU usage", "nexus_hw_cpu_usage", 0),
                _panel(2, "CPU frequency", "nexus_hw_cpu_frequency_hz", 0, x=12),
                _panel(3, "Threads", "nexus_hw_thread_count", 8),
                _panel(4, "SVE2 util", "nexus_hw_sve2_utilization", 8, x=12),
            ],
        ),
        "rmf-performix": _dashboard(
            "rmf-performix",
            "RMF Performix Dashboard",
            [
                _panel(1, "Available", "nexus_performix_available", 0),
                _panel(2, "IPC", "nexus_performix_ipc", 0, x=12),
                _panel(3, "Cache misses", "nexus_performix_cache_misses", 8),
                _panel(4, "Branch misses", "nexus_performix_branch_misses", 8, x=12),
            ],
        ),
        "rmf-planner-learning": _dashboard(
            "rmf-planner-learning",
            "RMF Planner Learning Dashboard",
            [
                _panel(1, "Planner accuracy", "nexus:planner_accuracy:avg5m", 0),
                _panel(2, "Cost error", "avg(nexus_planner_cost_error)", 0, x=12),
                _panel(3, "Route changes", "sum(rate(nexus_planner_route_changes_total[1m]))", 8),
                _panel(4, "Backend efficiency", "nexus:backend_efficiency:ratio5m", 8, x=12),
            ],
        ),
    }


def write_dashboards(directory: Path | str) -> list[Path]:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, payload in default_dashboards().items():
        path = root / f"{name}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(path)
    return written
