"""Typed Task Graph lifecycle events (OTel-ready payloads)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from .utils import utc_now


@dataclass(slots=True)
class TaskGraphEvent:
    """Base event envelope."""

    type: str
    graph_id: str
    node_id: str | None = None
    timestamp: datetime = field(default_factory=utc_now)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_otel_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "nexus.task_graph.event": self.type,
            "nexus.task_graph.graph_id": self.graph_id,
            "nexus.task_graph.event_id": self.event_id,
        }
        if self.node_id:
            attrs["nexus.task_graph.node_id"] = self.node_id
        for k, v in self.attributes.items():
            attrs[f"nexus.task_graph.{k}"] = v
        return attrs

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "graph_id": self.graph_id,
            "node_id": self.node_id,
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "attributes": dict(self.attributes),
        }


def NodeCreated(graph_id: str, node_id: str, **attrs: Any) -> TaskGraphEvent:
    return TaskGraphEvent("NodeCreated", graph_id, node_id, attributes=attrs)


def NodeStarted(graph_id: str, node_id: str, **attrs: Any) -> TaskGraphEvent:
    return TaskGraphEvent("NodeStarted", graph_id, node_id, attributes=attrs)


def NodeFinished(graph_id: str, node_id: str, **attrs: Any) -> TaskGraphEvent:
    return TaskGraphEvent("NodeFinished", graph_id, node_id, attributes=attrs)


def NodeFailed(graph_id: str, node_id: str, **attrs: Any) -> TaskGraphEvent:
    return TaskGraphEvent("NodeFailed", graph_id, node_id, attributes=attrs)


def NodeSkipped(graph_id: str, node_id: str, **attrs: Any) -> TaskGraphEvent:
    return TaskGraphEvent("NodeSkipped", graph_id, node_id, attributes=attrs)


def RetryStarted(graph_id: str, node_id: str, **attrs: Any) -> TaskGraphEvent:
    return TaskGraphEvent("RetryStarted", graph_id, node_id, attributes=attrs)


def Timeout(graph_id: str, node_id: str | None = None, **attrs: Any) -> TaskGraphEvent:
    return TaskGraphEvent("Timeout", graph_id, node_id, attributes=attrs)


def Cancellation(graph_id: str, node_id: str | None = None, **attrs: Any) -> TaskGraphEvent:
    return TaskGraphEvent("Cancellation", graph_id, node_id, attributes=attrs)


def Checkpoint(graph_id: str, node_id: str, **attrs: Any) -> TaskGraphEvent:
    return TaskGraphEvent("Checkpoint", graph_id, node_id, attributes=attrs)


def Restore(graph_id: str, node_id: str | None = None, **attrs: Any) -> TaskGraphEvent:
    return TaskGraphEvent("Restore", graph_id, node_id, attributes=attrs)


class EventBus:
    """In-memory pub/sub for Task Graph events."""

    def __init__(self) -> None:
        self._subs: list[Callable[[TaskGraphEvent], None]] = []
        self._history: list[TaskGraphEvent] = []

    def subscribe(self, handler: Callable[[TaskGraphEvent], None]) -> None:
        self._subs.append(handler)

    def emit(self, event: TaskGraphEvent) -> None:
        self._history.append(event)
        for handler in list(self._subs):
            handler(event)

    @property
    def history(self) -> list[TaskGraphEvent]:
        return list(self._history)

    def clear(self) -> None:
        self._history.clear()
