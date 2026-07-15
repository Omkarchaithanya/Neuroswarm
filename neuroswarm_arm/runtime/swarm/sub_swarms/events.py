"""Typed Sub Swarm events (OpenTelemetry-ready)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from ._utils import utc_now


@dataclass(slots=True)
class SwarmEvent:
    """Base event envelope for sub-swarm lifecycle."""

    type: str
    template_id: str | None = None
    timestamp: datetime = field(default_factory=utc_now)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_otel_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "nexus.sub_swarm.event": self.type,
            "nexus.sub_swarm.event_id": self.event_id,
        }
        if self.template_id:
            attrs["nexus.sub_swarm.template_id"] = self.template_id
        for k, v in self.attributes.items():
            attrs[f"nexus.sub_swarm.{k}"] = v
        return attrs

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "template_id": self.template_id,
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "attributes": dict(self.attributes),
        }


def SwarmRegistered(template_id: str, **attrs: Any) -> SwarmEvent:
    return SwarmEvent("SwarmRegistered", template_id, attributes=attrs)


def SwarmUpdated(template_id: str, **attrs: Any) -> SwarmEvent:
    return SwarmEvent("SwarmUpdated", template_id, attributes=attrs)


def SwarmSelected(template_id: str, **attrs: Any) -> SwarmEvent:
    return SwarmEvent("SwarmSelected", template_id, attributes=attrs)


def SwarmValidated(template_id: str, **attrs: Any) -> SwarmEvent:
    return SwarmEvent("SwarmValidated", template_id, attributes=attrs)


def SwarmDeprecated(template_id: str, **attrs: Any) -> SwarmEvent:
    return SwarmEvent("SwarmDeprecated", template_id, attributes=attrs)


def SwarmArchived(template_id: str, **attrs: Any) -> SwarmEvent:
    return SwarmEvent("SwarmArchived", template_id, attributes=attrs)


def SwarmDisabled(template_id: str, **attrs: Any) -> SwarmEvent:
    return SwarmEvent("SwarmDisabled", template_id, attributes=attrs)


def SelectionPerformed(**attrs: Any) -> SwarmEvent:
    return SwarmEvent("SelectionPerformed", attributes=attrs)


class EventBus:
    """Local in-process event bus (OTel sink later)."""

    def __init__(self) -> None:
        self._handlers: list[Callable[[SwarmEvent], None]] = []
        self._history: list[SwarmEvent] = []

    def subscribe(self, handler: Callable[[SwarmEvent], None]) -> None:
        self._handlers.append(handler)

    def emit(self, event: SwarmEvent) -> None:
        self._history.append(event)
        for handler in list(self._handlers):
            handler(event)

    def history(self, *, event_type: str | None = None) -> list[SwarmEvent]:
        if event_type is None:
            return list(self._history)
        return [e for e in self._history if e.type == event_type]

    def clear(self) -> None:
        self._history.clear()
