"""Query filters for Experience Store."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable

from .execution_record import ExecutionRecord

Predicate = Callable[[ExecutionRecord], bool]


@dataclass
class ExperienceFilter:
    """Composable AND-filter over execution records."""

    workflow_id: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    model: str | None = None
    backend: str | None = None
    success: bool | None = None
    tag: str | None = None
    tags: list[str] = field(default_factory=list)
    min_latency: float | None = None
    max_latency: float | None = None
    min_cost: float | None = None
    max_cost: float | None = None
    min_quality: float | None = None
    max_quality: float | None = None
    since: datetime | None = None
    until: datetime | None = None
    budget_envelope_id: str | None = None
    custom: list[Predicate] = field(default_factory=list)

    def matches(self, record: ExecutionRecord) -> bool:
        if self.workflow_id is not None and record.workflow_id != self.workflow_id:
            return False
        if self.request_id is not None and record.request_id != self.request_id:
            return False
        if self.session_id is not None and record.session_id != self.session_id:
            return False
        if self.success is not None and record.success != self.success:
            return False
        if self.agent_id is not None:
            agents = {a.agent_id for a in record.agent_assignments}
            if self.agent_id not in agents:
                return False
        if self.model is not None and self.model not in record.models_used:
            return False
        if self.backend is not None and self.backend not in record.backends_used:
            return False
        if self.tag is not None and self.tag not in record.tags:
            return False
        if self.tags and not set(self.tags).issubset(set(record.tags)):
            return False
        if self.min_latency is not None and record.latency < self.min_latency:
            return False
        if self.max_latency is not None and record.latency > self.max_latency:
            return False
        if self.min_cost is not None and record.estimated_cost < self.min_cost:
            return False
        if self.max_cost is not None and record.estimated_cost > self.max_cost:
            return False
        q = record.quality_score.score
        if self.min_quality is not None and q < self.min_quality:
            return False
        if self.max_quality is not None and q > self.max_quality:
            return False
        ts = record.timestamp
        if self.since is not None and ts < self.since:
            return False
        if self.until is not None and ts > self.until:
            return False
        if self.budget_envelope_id is not None:
            if record.budget is None or record.budget.envelope_id != self.budget_envelope_id:
                return False
        for pred in self.custom:
            if not pred(record):
                return False
        return True

    def apply(self, records: Iterable[ExecutionRecord]) -> list[ExecutionRecord]:
        return [r for r in records if self.matches(r)]


def by_workflow(workflow_id: str) -> ExperienceFilter:
    return ExperienceFilter(workflow_id=workflow_id)


def by_agent(agent_id: str) -> ExperienceFilter:
    return ExperienceFilter(agent_id=agent_id)


def by_model(model: str) -> ExperienceFilter:
    return ExperienceFilter(model=model)


def by_backend(backend: str) -> ExperienceFilter:
    return ExperienceFilter(backend=backend)


def by_success(success: bool = True) -> ExperienceFilter:
    return ExperienceFilter(success=success)


def by_date_range(since: datetime | None = None, until: datetime | None = None) -> ExperienceFilter:
    return ExperienceFilter(since=since, until=until)


def with_predicate(pred: Predicate, **kwargs: Any) -> ExperienceFilter:
    filt = ExperienceFilter(**kwargs)
    filt.custom.append(pred)
    return filt
