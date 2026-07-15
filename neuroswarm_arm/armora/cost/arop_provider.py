"""AROP ObservationProvider — read-only RCIS history as GEPA Actionable Side Information."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from neuroswarm_arm.evolution.interfaces.observation import ObservationProvider
from neuroswarm_arm.evolution.models.observation import (
    HealthStatus,
    ObservationSnapshot,
    RawObservation,
    TimeWindow,
)

from .runtime_cost import RuntimeCostIntelligence
from .schemas import safe_div


class RCISObservationProvider(ObservationProvider):
    """Expose RuntimeCostReport aggregates to AROP without mutating planner or envelopes."""

    name = "rcis"

    def __init__(self, rcis: RuntimeCostIntelligence) -> None:
        self.rcis = rcis

    def collect(self, window: TimeWindow) -> list[RawObservation]:
        reports = self.rcis.persistence.query_reports(limit=self.rcis.config.history_window)
        out: list[RawObservation] = []
        for report in reports:
            try:
                ts = datetime.fromisoformat(report.created_at.replace("Z", "+00:00"))
            except Exception:
                ts = datetime.now(timezone.utc)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts < window.start or ts > window.end:
                continue
            metrics = {
                "estimated_dollars": float(report.estimated_dollars),
                "latency_ms": float(report.latency_ms),
                "energy_joules": float(report.energy_estimate_joules),
                "cpu_seconds": float(report.cpu_seconds),
                "kv_reuse_ratio": float(report.kv_reuse_ratio),
                "spec_acceptance": float(report.speculation_acceptance_ratio),
                "tokens_per_dollar": float(report.tokens_per_dollar),
                "tokens_per_watt": float(report.tokens_per_watt),
                "quality_score": float(report.quality_score),
            }
            if report.prediction_errors is not None:
                metrics["prediction_cost_error"] = float(report.prediction_errors.cost_error)
                metrics["prediction_latency_error"] = float(
                    report.prediction_errors.latency_error
                )
                metrics["planner_accuracy"] = float(report.prediction_errors.planner_accuracy)
            out.append(
                RawObservation(
                    source=self.name,
                    collected_at=ts,
                    metrics=metrics,
                    labels={
                        "backend": report.backend,
                        "quantization": report.quantization,
                        "model_tier": report.model_tier,
                        "agent_id": report.agent_id,
                        "workflow_id": report.workflow_id,
                    },
                    payload={
                        "report_id": report.report_id,
                        "execution_id": report.execution_id,
                        "planner_decision_trace": report.planner_decision_trace,
                        "asi": {
                            "cost_breakdown": report.cost_breakdown.model_dump(),
                            "prediction_errors": (
                                report.prediction_errors.model_dump()
                                if report.prediction_errors
                                else None
                            ),
                        },
                    },
                )
            )
        return out

    def snapshot(self) -> ObservationSnapshot:
        reports = self.rcis.persistence.query_reports(limit=50)
        now = datetime.now(timezone.utc)
        if not reports:
            return ObservationSnapshot(collected_at=now, providers={self.name: {}}, aggregate={})
        n = float(len(reports))
        aggregate = {
            "runtime_cost_mean": safe_div(sum(r.estimated_dollars for r in reports), n),
            "runtime_latency_mean": safe_div(sum(r.latency_ms for r in reports), n),
            "runtime_energy_mean": safe_div(sum(r.energy_estimate_joules for r in reports), n),
            "runtime_kv_reuse_mean": safe_div(sum(r.kv_reuse_ratio for r in reports), n),
            "runtime_spec_acceptance_mean": safe_div(
                sum(r.speculation_acceptance_ratio for r in reports), n
            ),
            "runtime_planner_accuracy_mean": safe_div(
                sum(
                    (
                        r.prediction_errors.planner_accuracy
                        if r.prediction_errors is not None
                        else 1.0
                    )
                    for r in reports
                ),
                n,
            ),
        }
        return ObservationSnapshot(
            collected_at=now,
            providers={self.name: dict(aggregate)},
            aggregate=aggregate,
        )

    def metrics(self) -> dict[str, float]:
        snap = self.rcis.telemetry.snapshot()
        out: dict[str, float] = {}
        for k, v in snap.get("counters", {}).items():
            out[str(k).split("{", 1)[0]] = float(v)
        for k, v in snap.get("gauges", {}).items():
            out[str(k).split("{", 1)[0]] = float(v)
        return out

    def health(self) -> HealthStatus:
        try:
            _ = self.rcis.persistence.query_reports(limit=1)
            return HealthStatus(healthy=True, provider=self.name, details={"enabled": self.rcis.config.enabled})
        except Exception as exc:
            return HealthStatus(
                healthy=False,
                provider=self.name,
                details={"error": str(exc)},
            )
