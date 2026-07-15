"""Typed Checkpoint Manager events (OpenTelemetry-ready)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from ._utils import utc_now


@dataclass(slots=True)
class CheckpointEvent:
    """Base event envelope for checkpoint-manager lifecycle."""

    type: str
    checkpoint_id: str | None = None
    execution_id: str | None = None
    workflow_id: str | None = None
    timestamp: datetime = field(default_factory=utc_now)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_otel_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "nexus.swarm.checkpoint.event": self.type,
            "nexus.swarm.checkpoint.event_id": self.event_id,
        }
        if self.checkpoint_id:
            attrs["nexus.swarm.checkpoint.checkpoint_id"] = self.checkpoint_id
        if self.execution_id:
            attrs["nexus.swarm.checkpoint.execution_id"] = self.execution_id
        if self.workflow_id:
            attrs["nexus.swarm.checkpoint.workflow_id"] = self.workflow_id
        for k, v in self.attributes.items():
            attrs[f"nexus.swarm.checkpoint.{k}"] = v
        return attrs

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "checkpoint_id": self.checkpoint_id,
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "attributes": dict(self.attributes),
        }


def CheckpointCreated(
    checkpoint_id: str,
    *,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    **attrs: Any,
) -> CheckpointEvent:
    return CheckpointEvent(
        "CheckpointCreated",
        checkpoint_id=checkpoint_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        attributes=attrs,
    )


def CheckpointRestored(
    checkpoint_id: str,
    *,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    **attrs: Any,
) -> CheckpointEvent:
    return CheckpointEvent(
        "CheckpointRestored",
        checkpoint_id=checkpoint_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        attributes=attrs,
    )


def CheckpointArchived(
    checkpoint_id: str,
    *,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    **attrs: Any,
) -> CheckpointEvent:
    return CheckpointEvent(
        "CheckpointArchived",
        checkpoint_id=checkpoint_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        attributes=attrs,
    )


def CheckpointExpired(
    checkpoint_id: str,
    *,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    **attrs: Any,
) -> CheckpointEvent:
    return CheckpointEvent(
        "CheckpointExpired",
        checkpoint_id=checkpoint_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        attributes=attrs,
    )


def RecoveryPlanned(
    *,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    **attrs: Any,
) -> CheckpointEvent:
    return CheckpointEvent(
        "RecoveryPlanned",
        workflow_id=workflow_id,
        execution_id=execution_id,
        attributes=attrs,
    )


def RollbackPlanned(
    *,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    **attrs: Any,
) -> CheckpointEvent:
    return CheckpointEvent(
        "RollbackPlanned",
        workflow_id=workflow_id,
        execution_id=execution_id,
        attributes=attrs,
    )


def RetentionApplied(**attrs: Any) -> CheckpointEvent:
    return CheckpointEvent("RetentionApplied", attributes=attrs)


def ValidationFailed(
    *,
    checkpoint_id: str | None = None,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    **attrs: Any,
) -> CheckpointEvent:
    return CheckpointEvent(
        "ValidationFailed",
        checkpoint_id=checkpoint_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        attributes=attrs,
    )


class EventBus:
    """In-process pub/sub for checkpoint events."""

    def __init__(self) -> None:
        self._subs: list[Callable[[CheckpointEvent], None]] = []
        self._history: list[CheckpointEvent] = []

    def subscribe(self, handler: Callable[[CheckpointEvent], None]) -> None:
        self._subs.append(handler)

    def emit(self, event: CheckpointEvent) -> None:
        self._history.append(event)
        for handler in list(self._subs):
            handler(event)

    def history(self) -> list[CheckpointEvent]:
        return list(self._history)

    def clear(self) -> None:
        self._history.clear()
