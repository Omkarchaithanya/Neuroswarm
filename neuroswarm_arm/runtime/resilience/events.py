"""Typed RMRE events (OpenTelemetry-ready)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from ._utils import utc_now


@dataclass(slots=True)
class ResilienceEvent:
    """Base event envelope for RMRE lifecycle."""

    type: str
    execution_id: str | None = None
    policy_id: str | None = None
    model_id: str | None = None
    timestamp: datetime = field(default_factory=utc_now)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_otel_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "nexus.runtime.resilience.event": self.type,
            "nexus.runtime.resilience.event_id": self.event_id,
        }
        if self.execution_id:
            attrs["nexus.runtime.resilience.execution_id"] = self.execution_id
        if self.policy_id:
            attrs["nexus.runtime.resilience.policy_id"] = self.policy_id
        if self.model_id:
            attrs["nexus.runtime.resilience.model_id"] = self.model_id
        for k, v in self.attributes.items():
            attrs[f"nexus.runtime.resilience.{k}"] = v
        return attrs

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "execution_id": self.execution_id,
            "policy_id": self.policy_id,
            "model_id": self.model_id,
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "attributes": dict(self.attributes),
        }


def FallbackTriggered(
    *,
    execution_id: str | None = None,
    policy_id: str | None = None,
    model_id: str | None = None,
    **attrs: Any,
) -> ResilienceEvent:
    return ResilienceEvent(
        "FallbackTriggered",
        execution_id=execution_id,
        policy_id=policy_id,
        model_id=model_id,
        attributes=attrs,
    )


def CandidateGenerated(
    *,
    execution_id: str | None = None,
    policy_id: str | None = None,
    model_id: str | None = None,
    **attrs: Any,
) -> ResilienceEvent:
    return ResilienceEvent(
        "CandidateGenerated",
        execution_id=execution_id,
        policy_id=policy_id,
        model_id=model_id,
        attributes=attrs,
    )


def PolicyMatched(
    *,
    execution_id: str | None = None,
    policy_id: str | None = None,
    model_id: str | None = None,
    **attrs: Any,
) -> ResilienceEvent:
    return ResilienceEvent(
        "PolicyMatched",
        execution_id=execution_id,
        policy_id=policy_id,
        model_id=model_id,
        attributes=attrs,
    )


def RecoveryCompleted(
    *,
    execution_id: str | None = None,
    policy_id: str | None = None,
    model_id: str | None = None,
    **attrs: Any,
) -> ResilienceEvent:
    return ResilienceEvent(
        "RecoveryCompleted",
        execution_id=execution_id,
        policy_id=policy_id,
        model_id=model_id,
        attributes=attrs,
    )


def RecoveryFailed(
    *,
    execution_id: str | None = None,
    policy_id: str | None = None,
    model_id: str | None = None,
    **attrs: Any,
) -> ResilienceEvent:
    return ResilienceEvent(
        "RecoveryFailed",
        execution_id=execution_id,
        policy_id=policy_id,
        model_id=model_id,
        attributes=attrs,
    )


def HealthChanged(
    *,
    execution_id: str | None = None,
    policy_id: str | None = None,
    model_id: str | None = None,
    **attrs: Any,
) -> ResilienceEvent:
    return ResilienceEvent(
        "HealthChanged",
        execution_id=execution_id,
        policy_id=policy_id,
        model_id=model_id,
        attributes=attrs,
    )


class EventBus:
    """In-process pub/sub for RMRE events."""

    def __init__(self) -> None:
        self._subs: list[Callable[[ResilienceEvent], None]] = []
        self._history: list[ResilienceEvent] = []

    def subscribe(self, handler: Callable[[ResilienceEvent], None]) -> None:
        self._subs.append(handler)

    def emit(self, event: ResilienceEvent) -> None:
        self._history.append(event)
        for handler in list(self._subs):
            handler(event)

    def history(self) -> list[ResilienceEvent]:
        return list(self._history)

    def clear(self) -> None:
        self._history.clear()
