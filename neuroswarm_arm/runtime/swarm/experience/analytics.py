"""Analytics over immutable execution history."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .events import AnalyticsUpdated, EventBus
from .execution_record import ExecutionRecord
from .filters import ExperienceFilter
from .metrics import ExperienceMetrics
from .query import QueryEngine


@dataclass(frozen=True)
class AnalyticsReport:
    """Aggregate analytics snapshot (not stored as mutable state)."""

    count: int = 0
    success_count: int = 0
    failure_count: int = 0
    failure_rate: float = 0.0
    average_latency: float = 0.0
    average_cost: float = 0.0
    average_quality: float = 0.0
    average_retries: float = 0.0
    retry_frequency: float = 0.0
    budget_efficiency: float = 0.0
    model_utilization: dict[str, int] = field(default_factory=dict)
    agent_utilization: dict[str, int] = field(default_factory=dict)
    backend_utilization: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "failure_rate": self.failure_rate,
            "average_latency": self.average_latency,
            "average_cost": self.average_cost,
            "average_quality": self.average_quality,
            "average_retries": self.average_retries,
            "retry_frequency": self.retry_frequency,
            "budget_efficiency": self.budget_efficiency,
            "model_utilization": dict(self.model_utilization),
            "agent_utilization": dict(self.agent_utilization),
            "backend_utilization": dict(self.backend_utilization),
        }


class ExperienceAnalytics:
    """Compute aggregates over query results."""

    def __init__(
        self,
        query: QueryEngine,
        *,
        events: EventBus | None = None,
        metrics: ExperienceMetrics | None = None,
    ) -> None:
        self.query = query
        self.events = events or EventBus()
        self.metrics = metrics or ExperienceMetrics()

    def compute(self, filt: ExperienceFilter | None = None) -> AnalyticsReport:
        records = self.query.filter(filt)
        report = self._from_records(records)
        self.metrics.incr("analytics_runs")
        self.events.emit(AnalyticsUpdated(count=report.count, failure_rate=report.failure_rate))
        return report

    def _from_records(self, records: list[ExecutionRecord]) -> AnalyticsReport:
        n = len(records)
        if n == 0:
            return AnalyticsReport()
        successes = sum(1 for r in records if r.success)
        failures = n - successes
        total_latency = sum(r.latency for r in records)
        total_cost = sum(r.estimated_cost for r in records)
        total_quality = sum(r.quality_score.score for r in records)
        total_retries = sum(r.retry_count for r in records)
        retried = sum(1 for r in records if r.retry_count > 0)

        models: Counter[str] = Counter()
        agents: Counter[str] = Counter()
        backends: Counter[str] = Counter()
        budget_eff_sum = 0.0
        budget_eff_n = 0
        for r in records:
            for m in r.models_used:
                models[m] += 1
            for a in r.agent_assignments:
                agents[a.agent_id] += 1
            for b in r.backends_used:
                backends[b] += 1
            eff = self._budget_efficiency(r)
            if eff is not None:
                budget_eff_sum += eff
                budget_eff_n += 1

        return AnalyticsReport(
            count=n,
            success_count=successes,
            failure_count=failures,
            failure_rate=failures / n,
            average_latency=total_latency / n,
            average_cost=total_cost / n,
            average_quality=total_quality / n,
            average_retries=total_retries / n,
            retry_frequency=retried / n,
            budget_efficiency=(budget_eff_sum / budget_eff_n) if budget_eff_n else 0.0,
            model_utilization=dict(models),
            agent_utilization=dict(agents),
            backend_utilization=dict(backends),
        )

    @staticmethod
    def _budget_efficiency(record: ExecutionRecord) -> float | None:
        """Cost used vs budget max — closer to 1 means efficient use without overrun.

        efficiency = 1 - min(1, cost / max_cost) when under budget; 0 if over.
        """
        if record.budget is None or record.budget.max_cost_usd is None:
            return None
        max_cost = float(record.budget.max_cost_usd)
        if max_cost <= 0:
            return None
        ratio = record.estimated_cost / max_cost
        if ratio > 1.0:
            return 0.0
        return 1.0 - ratio
