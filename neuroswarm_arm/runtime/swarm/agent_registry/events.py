"""Typed Agent Registry events (OpenTelemetry-ready)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from ._utils import utc_now


@dataclass(slots=True)
class RegistryEvent:
    """Base event envelope for registry lifecycle."""

    type: str
    agent_id: str | None = None
    timestamp: datetime = field(default_factory=utc_now)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_otel_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "nexus.agent_registry.event": self.type,
            "nexus.agent_registry.event_id": self.event_id,
        }
        if self.agent_id:
            attrs["nexus.agent_registry.agent_id"] = self.agent_id
        for k, v in self.attributes.items():
            attrs[f"nexus.agent_registry.{k}"] = v
        return attrs

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "attributes": dict(self.attributes),
        }


def AgentRegistered(agent_id: str, **attrs: Any) -> RegistryEvent:
    return RegistryEvent("AgentRegistered", agent_id, attributes=attrs)


def AgentUpdated(agent_id: str, **attrs: Any) -> RegistryEvent:
    return RegistryEvent("AgentUpdated", agent_id, attributes=attrs)


def AgentRemoved(agent_id: str, **attrs: Any) -> RegistryEvent:
    return RegistryEvent("AgentRemoved", agent_id, attributes=attrs)


def AgentEnabled(agent_id: str, **attrs: Any) -> RegistryEvent:
    return RegistryEvent("AgentEnabled", agent_id, attributes=attrs)


def AgentDisabled(agent_id: str, **attrs: Any) -> RegistryEvent:
    return RegistryEvent("AgentDisabled", agent_id, attributes=attrs)


def Heartbeat(agent_id: str, **attrs: Any) -> RegistryEvent:
    return RegistryEvent("Heartbeat", agent_id, attributes=attrs)


def HealthChanged(agent_id: str, **attrs: Any) -> RegistryEvent:
    return RegistryEvent("HealthChanged", agent_id, attributes=attrs)


def CapabilityChanged(agent_id: str, **attrs: Any) -> RegistryEvent:
    return RegistryEvent("CapabilityChanged", agent_id, attributes=attrs)


def SelectionPerformed(**attrs: Any) -> RegistryEvent:
    return RegistryEvent("SelectionPerformed", None, attributes=attrs)


class EventBus:
    """In-memory pub/sub for registry events."""

    def __init__(self, *, max_history: int = 10_000) -> None:
        self._subs: list[Callable[[RegistryEvent], None]] = []
        self._history: list[RegistryEvent] = []
        self._max_history = max_history

    def subscribe(self, handler: Callable[[RegistryEvent], None]) -> None:
        self._subs.append(handler)

    def unsubscribe(self, handler: Callable[[RegistryEvent], None]) -> None:
        self._subs = [h for h in self._subs if h is not handler]

    def emit(self, event: RegistryEvent) -> None:
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]
        for handler in list(self._subs):
            handler(event)

    def history(self, *, event_type: str | None = None) -> list[RegistryEvent]:
        if event_type is None:
            return list(self._history)
        return [e for e in self._history if e.type == event_type]

    def clear(self) -> None:
        self._history.clear()
