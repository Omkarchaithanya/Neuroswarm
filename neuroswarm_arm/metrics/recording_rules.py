"""Prometheus recording rules for RMF SLI rollups."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class RecordingRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: str
    expr: str
    labels: dict[str, str] = Field(default_factory=dict)


class RecordingGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    interval: str = "30s"
    rules: list[RecordingRule]


def default_recording_groups() -> list[RecordingGroup]:
    return [
        RecordingGroup(
            name="nexus_rmf_latency",
            rules=[
                RecordingRule(
                    record="nexus:request_duration_seconds:avg5m",
                    expr="sum(rate(nexus_request_duration_seconds_sum[5m])) / clamp_min(sum(rate(nexus_request_duration_seconds_count[5m])), 1)",
                ),
                RecordingRule(
                    record="nexus:request_duration_seconds:p95_5m",
                    expr="histogram_quantile(0.95, sum(rate(nexus_request_duration_seconds_bucket[5m])) by (le))",
                ),
                RecordingRule(
                    record="nexus:request_duration_seconds:p99_5m",
                    expr="histogram_quantile(0.99, sum(rate(nexus_request_duration_seconds_bucket[5m])) by (le))",
                ),
                RecordingRule(
                    record="nexus:planner_latency_seconds:avg5m",
                    expr="sum(rate(nexus_planner_latency_seconds_sum[5m])) / clamp_min(sum(rate(nexus_planner_latency_seconds_count[5m])), 1)",
                ),
                RecordingRule(
                    record="nexus:dipa_prefill_latency_seconds:p95_5m",
                    expr="histogram_quantile(0.95, sum(rate(nexus_dipa_prefill_latency_seconds_bucket[5m])) by (le))",
                ),
            ],
        ),
        RecordingGroup(
            name="nexus_rmf_efficiency",
            rules=[
                RecordingRule(
                    record="nexus:cost_per_request:avg5m",
                    expr="avg_over_time(nexus_cost_per_request[5m])",
                ),
                RecordingRule(
                    record="nexus:cpu_usage:avg5m",
                    expr="avg_over_time(nexus_hw_cpu_usage[5m])",
                ),
                RecordingRule(
                    record="nexus:memory_rss_bytes:avg5m",
                    expr="avg_over_time(nexus_memory_rss_bytes[5m])",
                ),
                RecordingRule(
                    record="nexus:kv_cache_reuse:avg5m",
                    expr="avg_over_time(nexus_kv_cache_reuse[5m])",
                ),
                RecordingRule(
                    record="nexus:planner_accuracy:avg5m",
                    expr="1 - clamp_max(avg_over_time(nexus_planner_prediction_error[5m]), 1)",
                ),
                RecordingRule(
                    record="nexus:backend_efficiency:ratio5m",
                    expr="sum(rate(nexus_routing_backend_usage_total{status=\"ok\"}[5m])) / clamp_min(sum(rate(nexus_routing_backend_usage_total[5m])), 1)",
                ),
                RecordingRule(
                    record="nexus:quantization_efficiency:ratio5m",
                    expr="sum(rate(nexus_routing_quantization_usage_total{status=\"ok\"}[5m])) / clamp_min(sum(rate(nexus_routing_quantization_usage_total[5m])), 1)",
                ),
            ],
        ),
    ]


def render_recording_yaml(groups: list[RecordingGroup] | None = None) -> str:
    groups = groups or default_recording_groups()
    payload: dict[str, Any] = {
        "groups": [
            {
                "name": g.name,
                "interval": g.interval,
                "rules": [
                    {"record": r.record, "expr": r.expr, **({"labels": r.labels} if r.labels else {})}
                    for r in g.rules
                ],
            }
            for g in groups
        ]
    }
    return yaml.safe_dump(payload, sort_keys=False)


def write_recording_rules(path: Path | str) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_recording_yaml(), encoding="utf-8")
    return out
