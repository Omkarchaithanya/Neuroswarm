"""Async-friendly in-process event bus for AROP pipeline events."""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Mapping


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AROPEventType(str, Enum):
    OBSERVATION_COLLECTED = "observation_collected"
    KNOWLEDGE_UPDATED = "knowledge_updated"
    POLICY_PROPOSED = "policy_proposed"
    POLICY_MATERIALIZED = "policy_materialized"
    OFFLINE_EVAL_DONE = "offline_eval_done"
    SHADOW_DONE = "shadow_done"
    VALIDATION_DONE = "validation_done"
    SAFETY_DONE = "safety_done"
    CANARY_DEPLOYED = "canary_deployed"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
    PIPELINE_COMPLETE = "pipeline_complete"
    PIPELINE_REJECTED = "pipeline_rejected"


@dataclass(frozen=True, slots=True)
class AROPEvent:
    type: AROPEventType
    payload: Mapping[str, Any] = field(default_factory=dict)
    at: datetime = field(default_factory=_utcnow)


Listener = Callable[[AROPEvent], None]


class EventBus:
    """Thread-safe sync bus with optional async fan-out."""

    def __init__(self) -> None:
        self._listeners: dict[AROPEventType | None, list[Listener]] = defaultdict(list)
        self._lock = threading.RLock()
        self._history: list[AROPEvent] = []
        self._max_history = 500

    def subscribe(self, event_type: AROPEventType | None, listener: Listener) -> None:
        with self._lock:
            self._listeners[event_type].append(listener)

    def publish(self, event: AROPEvent) -> None:
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]
            targets = list(self._listeners.get(event.type, [])) + list(self._listeners.get(None, []))
        for listener in targets:
            try:
                listener(event)
            except Exception:
                continue

    def emit(self, event_type: AROPEventType, **payload: Any) -> AROPEvent:
        event = AROPEvent(type=event_type, payload=payload)
        self.publish(event)
        return event

    def history(self, *, limit: int = 50) -> list[AROPEvent]:
        with self._lock:
            return list(self._history[-limit:])

    async def publish_async(self, event: AROPEvent) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.publish, event)
