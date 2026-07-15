"""Router event types for telemetry and hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import time
from typing import Any


class RouterEventKind(str, Enum):
    TOOL_REGISTERED = "tool_registered"
    TOOL_UPDATED = "tool_updated"
    TOOL_REMOVED = "tool_removed"
    INDEX_REBUILT = "index_rebuilt"
    INDEX_INCREMENTAL = "index_incremental"
    ROUTED = "routed"
    SNAPSHOT = "snapshot"
    RESTORE = "restore"
    RELOAD = "reload"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    BACKEND_FALLBACK = "backend_fallback"
    HEALTH = "health"


@dataclass(slots=True)
class RouterEvent:
    kind: RouterEventKind
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "payload": self.payload, "ts": self.ts}


class RouterEventBus:
    def __init__(self, *, maxlen: int = 10_000) -> None:
        self._events: list[RouterEvent] = []
        self._maxlen = maxlen
        self._listeners: list[Any] = []

    def emit(self, kind: RouterEventKind, **payload: Any) -> RouterEvent:
        event = RouterEvent(kind=kind, payload=payload)
        self._events.append(event)
        if len(self._events) > self._maxlen:
            self._events = self._events[-self._maxlen :]
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass
        return event

    def subscribe(self, listener: Any) -> None:
        self._listeners.append(listener)

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._events[-limit:]]
