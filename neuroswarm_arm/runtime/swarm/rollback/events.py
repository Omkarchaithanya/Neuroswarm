"""Typed Rollback Manager events (OpenTelemetry-ready)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from ._utils import utc_now


@dataclass(slots=True)
class RollbackEvent:
    """Base event envelope for rollback-manager lifecycle."""

    type: str
    rollback_id: str | None = None
    execution_id: str | None = None
    workflow_id: str | None = None
    timestamp: datetime = field(default_factory=utc_now)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_otel_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "nexus.swarm.rollback.event": self.type,
            "nexus.swarm.rollback.event_id": self.event_id,
        }
        if self.rollback_id:
            attrs["nexus.swarm.rollback.rollback_id"] = self.rollback_id
        if self.execution_id:
            attrs["nexus.swarm.rollback.execution_id"] = self.execution_id
        if self.workflow_id:
            attrs["nexus.swarm.rollback.workflow_id"] = self.workflow_id
        for k, v in self.attributes.items():
            attrs[f"nexus.swarm.rollback.{k}"] = v
        return attrs

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "rollback_id": self.rollback_id,
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "attributes": dict(self.attributes),
        }


def RollbackStarted(
    rollback_id: str,
    *,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    **attrs: Any,
) -> RollbackEvent:
    return RollbackEvent(
        "RollbackStarted",
        rollback_id=rollback_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        attributes=attrs,
    )


def RollbackCompleted(
    rollback_id: str,
    *,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    **attrs: Any,
) -> RollbackEvent:
    return RollbackEvent(
        "RollbackCompleted",
        rollback_id=rollback_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        attributes=attrs,
    )


def RollbackFailed(
    rollback_id: str,
    *,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    **attrs: Any,
) -> RollbackEvent:
    return RollbackEvent(
        "RollbackFailed",
        rollback_id=rollback_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        attributes=attrs,
    )


def RollbackCancelled(
    rollback_id: str,
    *,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    **attrs: Any,
) -> RollbackEvent:
    return RollbackEvent(
        "RollbackCancelled",
        rollback_id=rollback_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        attributes=attrs,
    )


def RollbackValidated(
    rollback_id: str,
    *,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    **attrs: Any,
) -> RollbackEvent:
    return RollbackEvent(
        "RollbackValidated",
        rollback_id=rollback_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        attributes=attrs,
    )


def RecoveryPrepared(
    rollback_id: str,
    *,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    **attrs: Any,
) -> RollbackEvent:
    return RollbackEvent(
        "RecoveryPrepared",
        rollback_id=rollback_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        attributes=attrs,
    )


def RecoveryFinished(
    rollback_id: str,
    *,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    **attrs: Any,
) -> RollbackEvent:
    return RollbackEvent(
        "RecoveryFinished",
        rollback_id=rollback_id,
        workflow_id=workflow_id,
        execution_id=execution_id,
        attributes=attrs,
    )


class EventBus:
    """In-process pub/sub for rollback events."""

    def __init__(self) -> None:
        self._subs: list[Callable[[RollbackEvent], None]] = []
        self._history: list[RollbackEvent] = []

    def subscribe(self, handler: Callable[[RollbackEvent], None]) -> None:
        self._subs.append(handler)

    def emit(self, event: RollbackEvent) -> None:
        self._history.append(event)
        for handler in list(self._subs):
            handler(event)

    def history(self) -> list[RollbackEvent]:
        return list(self._history)

    def clear(self) -> None:
        self._history.clear()
