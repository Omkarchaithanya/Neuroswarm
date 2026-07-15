"""Alertmanager rule models and emitters for RMF."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class AlertRule(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    alert: str
    expr: str
    for_duration: str = Field(default="2m", alias="for")
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)

    def to_prom(self) -> dict[str, Any]:
        return {
            "alert": self.alert,
            "expr": self.expr,
            "for": self.for_duration,
            "labels": self.labels,
            "annotations": self.annotations,
        }


class AlertGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    rules: list[AlertRule]


def default_alert_groups() -> list[AlertGroup]:
    sev = {"severity": "page"}
    warn = {"severity": "warning"}
    return [
        AlertGroup(
            name="nexus_rmf_runtime",
            rules=[
                AlertRule(
                    alert="NexusHighLatency",
                    expr='histogram_quantile(0.95, sum(rate(nexus_request_duration_seconds_bucket[5m])) by (le)) > 5',
                    for_duration="5m",
                    labels=sev,
                    annotations={
                        "summary": "P95 request latency high",
                        "description": "P95 nexus_request_duration_seconds > 5s for 5m",
                    },
                ),
                AlertRule(
                    alert="NexusPlannerFailure",
                    expr="increase(nexus_planner_budget_violations_total[5m]) > 5 or increase(nexus_admission_failures_total[5m]) > 10",
                    for_duration="3m",
                    labels=sev,
                    annotations={"summary": "Planner / admission failures elevated"},
                ),
                AlertRule(
                    alert="NexusBackendFailure",
                    expr='sum(rate(nexus_routing_failures_total[5m])) > 0.2 or sum(rate(nexus_request_failed_total{status="error"}[5m])) > 0.5',
                    for_duration="3m",
                    labels=sev,
                    annotations={"summary": "Backend or request failures elevated"},
                ),
                AlertRule(
                    alert="NexusBudgetExhaustion",
                    expr="min(nexus_budget_remaining) < 0.05 or min(nexus_budget_token_remaining) < 64",
                    for_duration="2m",
                    labels=sev,
                    annotations={"summary": "Budget nearly exhausted"},
                ),
                AlertRule(
                    alert="NexusMemoryPressure",
                    expr="nexus_memory_rss_bytes > 12e9 or nexus_hw_memory_usage_bytes > 12e9",
                    for_duration="5m",
                    labels=warn,
                    annotations={"summary": "Process memory pressure"},
                ),
                AlertRule(
                    alert="NexusKVCachePressure",
                    expr="nexus_kv_cache_reuse < 0.2 and rate(nexus_kv_cache_evictions_total[5m]) > 10",
                    for_duration="5m",
                    labels=warn,
                    annotations={"summary": "KV cache pressure / low reuse"},
                ),
                AlertRule(
                    alert="NexusWorkerSaturation",
                    expr="avg(nexus_haoe_worker_utilization) > 0.9",
                    for_duration="5m",
                    labels=sev,
                    annotations={"summary": "HAOE workers saturated"},
                ),
                AlertRule(
                    alert="NexusHighQueueDepth",
                    expr="nexus_haoe_queue_depth > 100 or nexus_admission_queue > 50",
                    for_duration="3m",
                    labels=warn,
                    annotations={"summary": "Scheduler or admission queue deep"},
                ),
                AlertRule(
                    alert="NexusSpeculativeFailure",
                    expr="sum(rate(nexus_dipa_speculative_rejection_total[5m])) / clamp_min(sum(rate(nexus_dipa_speculative_acceptance_total[5m])) + sum(rate(nexus_dipa_speculative_rejection_total[5m])), 1) > 0.8",
                    for_duration="5m",
                    labels=warn,
                    annotations={"summary": "Speculative decoding rejection ratio high"},
                ),
                AlertRule(
                    alert="NexusStreamingFailure",
                    expr='sum(rate(nexus_request_failed_total{streaming="true"}[5m])) > 0.2',
                    for_duration="3m",
                    labels=sev,
                    annotations={"summary": "Streaming request failures"},
                ),
                AlertRule(
                    alert="NexusPlannerPredictionError",
                    expr="avg(nexus_planner_prediction_error) > 0.5 or avg(nexus_planner_cost_error) > 0.5",
                    for_duration="10m",
                    labels=warn,
                    annotations={"summary": "Planner prediction error elevated"},
                ),
                AlertRule(
                    alert="NexusEnergySpike",
                    expr="avg_over_time(nexus_energy_estimated_power_watts[5m]) > 2 * avg_over_time(nexus_energy_estimated_power_watts[1h])",
                    for_duration="5m",
                    labels=warn,
                    annotations={"summary": "Energy / power spike vs hourly baseline"},
                ),
                AlertRule(
                    alert="NexusCPUSaturation",
                    expr="avg(nexus_hw_cpu_usage) > 0.9",
                    for_duration="5m",
                    labels=sev,
                    annotations={"summary": "CPU saturation"},
                ),
            ],
        )
    ]


def render_alert_yaml(groups: list[AlertGroup] | None = None) -> str:
    groups = groups or default_alert_groups()
    payload = {
        "groups": [
            {"name": g.name, "rules": [r.to_prom() for r in g.rules]} for g in groups
        ]
    }
    return yaml.safe_dump(payload, sort_keys=False)


def write_alert_rules(path: Path | str) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_alert_yaml(), encoding="utf-8")
    return out
