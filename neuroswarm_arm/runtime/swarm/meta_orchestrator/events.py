"""Typed Meta Orchestrator lifecycle events (OTel-ready payloads)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from ._utils import utc_now


@dataclass(slots=True)
class OrchestratorEvent:
    """Base event envelope."""

    type: str
    workflow_id: str | None = None
    execution_id: str | None = None
    node_id: str | None = None
    timestamp: datetime = field(default_factory=utc_now)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_otel_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "nexus.meta_orchestrator.event": self.type,
            "nexus.meta_orchestrator.event_id": self.event_id,
        }
        if self.workflow_id:
            attrs["nexus.meta_orchestrator.workflow_id"] = self.workflow_id
        if self.execution_id:
            attrs["nexus.meta_orchestrator.execution_id"] = self.execution_id
        if self.node_id:
            attrs["nexus.meta_orchestrator.node_id"] = self.node_id
        for k, v in self.attributes.items():
            attrs[f"nexus.meta_orchestrator.{k}"] = v
        return attrs

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "node_id": self.node_id,
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "attributes": dict(self.attributes),
        }


def WorkflowCreated(workflow_id: str, execution_id: str, **attrs: Any) -> OrchestratorEvent:
    return OrchestratorEvent(
        "WorkflowCreated", workflow_id=workflow_id, execution_id=execution_id, attributes=attrs
    )


def WorkflowStarted(workflow_id: str, execution_id: str, **attrs: Any) -> OrchestratorEvent:
    return OrchestratorEvent(
        "WorkflowStarted", workflow_id=workflow_id, execution_id=execution_id, attributes=attrs
    )


def NodeAssigned(
    workflow_id: str, execution_id: str, node_id: str, **attrs: Any
) -> OrchestratorEvent:
    return OrchestratorEvent(
        "NodeAssigned",
        workflow_id=workflow_id,
        execution_id=execution_id,
        node_id=node_id,
        attributes=attrs,
    )


def NodeCompleted(
    workflow_id: str, execution_id: str, node_id: str, **attrs: Any
) -> OrchestratorEvent:
    return OrchestratorEvent(
        "NodeCompleted",
        workflow_id=workflow_id,
        execution_id=execution_id,
        node_id=node_id,
        attributes=attrs,
    )


def NodeFailed(
    workflow_id: str, execution_id: str, node_id: str, **attrs: Any
) -> OrchestratorEvent:
    return OrchestratorEvent(
        "NodeFailed",
        workflow_id=workflow_id,
        execution_id=execution_id,
        node_id=node_id,
        attributes=attrs,
    )


def WorkflowCompleted(workflow_id: str, execution_id: str, **attrs: Any) -> OrchestratorEvent:
    return OrchestratorEvent(
        "WorkflowCompleted", workflow_id=workflow_id, execution_id=execution_id, attributes=attrs
    )


def WorkflowCancelled(workflow_id: str, execution_id: str, **attrs: Any) -> OrchestratorEvent:
    return OrchestratorEvent(
        "WorkflowCancelled", workflow_id=workflow_id, execution_id=execution_id, attributes=attrs
    )


def CheckpointCreated(workflow_id: str, execution_id: str, **attrs: Any) -> OrchestratorEvent:
    return OrchestratorEvent(
        "CheckpointCreated", workflow_id=workflow_id, execution_id=execution_id, attributes=attrs
    )


def CheckpointRestored(workflow_id: str, execution_id: str, **attrs: Any) -> OrchestratorEvent:
    return OrchestratorEvent(
        "CheckpointRestored", workflow_id=workflow_id, execution_id=execution_id, attributes=attrs
    )


def AggregationFinished(workflow_id: str, execution_id: str, **attrs: Any) -> OrchestratorEvent:
    return OrchestratorEvent(
        "AggregationFinished", workflow_id=workflow_id, execution_id=execution_id, attributes=attrs
    )


def RetryRequested(
    workflow_id: str, execution_id: str, node_id: str, **attrs: Any
) -> OrchestratorEvent:
    return OrchestratorEvent(
        "RetryRequested",
        workflow_id=workflow_id,
        execution_id=execution_id,
        node_id=node_id,
        attributes=attrs,
    )


def RollbackNotified(workflow_id: str, execution_id: str, **attrs: Any) -> OrchestratorEvent:
    return OrchestratorEvent(
        "RollbackNotified", workflow_id=workflow_id, execution_id=execution_id, attributes=attrs
    )


def BarrierReleased(
    workflow_id: str, execution_id: str, node_id: str, **attrs: Any
) -> OrchestratorEvent:
    return OrchestratorEvent(
        "BarrierReleased",
        workflow_id=workflow_id,
        execution_id=execution_id,
        node_id=node_id,
        attributes=attrs,
    )


class EventBus:
    """In-memory pub/sub for orchestrator events."""

    def __init__(self, *, max_history: int = 10_000) -> None:
        self._subs: list[Callable[[OrchestratorEvent], None]] = []
        self._history: list[OrchestratorEvent] = []
        self._max_history = max_history

    def subscribe(self, handler: Callable[[OrchestratorEvent], None]) -> None:
        self._subs.append(handler)

    def unsubscribe(self, handler: Callable[[OrchestratorEvent], None]) -> None:
        self._subs = [h for h in self._subs if h is not handler]

    def emit(self, event: OrchestratorEvent) -> None:
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]
        for handler in list(self._subs):
            handler(event)

    def history(self) -> list[OrchestratorEvent]:
        return list(self._history)

    def clear(self) -> None:
        self._history.clear()
