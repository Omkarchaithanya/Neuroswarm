"""Typed Swarm Context lifecycle events (OTel-ready)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from ._utils import utc_now


@dataclass(slots=True)
class ContextEvent:
    """Base event envelope for Context OS lifecycle."""

    type: str
    context_id: str | None = None
    timestamp: datetime = field(default_factory=utc_now)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_otel_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "nexus.swarm.context.event": self.type,
            "nexus.swarm.context.event_id": self.event_id,
        }
        if self.context_id:
            attrs["nexus.swarm.context.context_id"] = self.context_id
        for k, v in self.attributes.items():
            attrs[f"nexus.swarm.context.{k}"] = v
        return attrs

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "context_id": self.context_id,
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "attributes": dict(self.attributes),
        }


def ContextCreated(context_id: str, **attrs: Any) -> ContextEvent:
    return ContextEvent("ContextCreated", context_id, attributes=attrs)


def ContextUpdated(context_id: str, **attrs: Any) -> ContextEvent:
    return ContextEvent("ContextUpdated", context_id, attributes=attrs)


def SnapshotCreated(context_id: str, **attrs: Any) -> ContextEvent:
    return ContextEvent("SnapshotCreated", context_id, attributes=attrs)


def SnapshotRestored(context_id: str, **attrs: Any) -> ContextEvent:
    return ContextEvent("SnapshotRestored", context_id, attributes=attrs)


def BudgetUpdated(context_id: str, **attrs: Any) -> ContextEvent:
    return ContextEvent("BudgetUpdated", context_id, attributes=attrs)


def MemoryUpdated(context_id: str, **attrs: Any) -> ContextEvent:
    return ContextEvent("MemoryUpdated", context_id, attributes=attrs)


def ExecutionUpdated(context_id: str, **attrs: Any) -> ContextEvent:
    return ContextEvent("ExecutionUpdated", context_id, attributes=attrs)


def KnowledgeUpdated(context_id: str, **attrs: Any) -> ContextEvent:
    return ContextEvent("KnowledgeUpdated", context_id, attributes=attrs)


def ToolUpdated(context_id: str, **attrs: Any) -> ContextEvent:
    return ContextEvent("ToolUpdated", context_id, attributes=attrs)


def CheckpointCreated(context_id: str, **attrs: Any) -> ContextEvent:
    return ContextEvent("CheckpointCreated", context_id, attributes=attrs)


def CheckpointRestored(context_id: str, **attrs: Any) -> ContextEvent:
    return ContextEvent("CheckpointRestored", context_id, attributes=attrs)


class EventBus:
    """Thread-safe fan-out for ContextEvent subscribers."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: list[Callable[[ContextEvent], None]] = []
        self._history: list[ContextEvent] = []
        self._max_history = 10_000

    def subscribe(self, handler: Callable[[ContextEvent], None]) -> None:
        with self._lock:
            self._subscribers.append(handler)

    def unsubscribe(self, handler: Callable[[ContextEvent], None]) -> None:
        with self._lock:
            self._subscribers = [h for h in self._subscribers if h is not handler]

    def emit(self, event: ContextEvent) -> None:
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]
            handlers = list(self._subscribers)
        for h in handlers:
            h(event)

    def history(self) -> list[ContextEvent]:
        with self._lock:
            return list(self._history)

    def clear(self) -> None:
        with self._lock:
            self._history.clear()
