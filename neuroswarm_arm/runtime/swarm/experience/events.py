"""Typed Experience Store events (OpenTelemetry-ready)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from ._utils import utc_now


@dataclass(slots=True)
class ExperienceEvent:
    """Base event envelope for experience-store lifecycle."""

    type: str
    execution_id: str | None = None
    workflow_id: str | None = None
    timestamp: datetime = field(default_factory=utc_now)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_otel_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "nexus.swarm.experience.event": self.type,
            "nexus.swarm.experience.event_id": self.event_id,
        }
        if self.execution_id:
            attrs["nexus.swarm.experience.execution_id"] = self.execution_id
        if self.workflow_id:
            attrs["nexus.swarm.experience.workflow_id"] = self.workflow_id
        for k, v in self.attributes.items():
            attrs[f"nexus.swarm.experience.{k}"] = v
        return attrs

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "attributes": dict(self.attributes),
        }


def ExecutionRecorded(
    execution_id: str, workflow_id: str | None = None, **attrs: Any
) -> ExperienceEvent:
    return ExperienceEvent(
        "ExecutionRecorded",
        execution_id=execution_id,
        workflow_id=workflow_id,
        attributes=attrs,
    )


def ExecutionArchived(
    execution_id: str, workflow_id: str | None = None, **attrs: Any
) -> ExperienceEvent:
    return ExperienceEvent(
        "ExecutionArchived",
        execution_id=execution_id,
        workflow_id=workflow_id,
        attributes=attrs,
    )


def ExecutionExported(
    execution_id: str | None = None, workflow_id: str | None = None, **attrs: Any
) -> ExperienceEvent:
    return ExperienceEvent(
        "ExecutionExported",
        execution_id=execution_id,
        workflow_id=workflow_id,
        attributes=attrs,
    )


def DatasetGenerated(kind: str, **attrs: Any) -> ExperienceEvent:
    return ExperienceEvent(
        "DatasetGenerated",
        attributes={"kind": kind, **attrs},
    )


def AnalyticsUpdated(**attrs: Any) -> ExperienceEvent:
    return ExperienceEvent("AnalyticsUpdated", attributes=attrs)


def WorkflowRecorded(workflow_id: str, **attrs: Any) -> ExperienceEvent:
    return ExperienceEvent(
        "WorkflowRecorded",
        workflow_id=workflow_id,
        attributes=attrs,
    )


class EventBus:
    """In-memory pub/sub for experience events."""

    def __init__(self, *, max_history: int = 10_000) -> None:
        self._subs: list[Callable[[ExperienceEvent], None]] = []
        self._history: list[ExperienceEvent] = []
        self._max_history = max_history

    def subscribe(self, handler: Callable[[ExperienceEvent], None]) -> None:
        self._subs.append(handler)

    def unsubscribe(self, handler: Callable[[ExperienceEvent], None]) -> None:
        self._subs = [h for h in self._subs if h is not handler]

    def emit(self, event: ExperienceEvent) -> None:
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]
        for handler in list(self._subs):
            handler(event)

    def history(self, *, event_type: str | None = None) -> list[ExperienceEvent]:
        if event_type is None:
            return list(self._history)
        return [e for e in self._history if e.type == event_type]

    def clear(self) -> None:
        self._history.clear()
