"""In-process pub/sub EventBus — Observer pattern, no tight coupling."""

from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Any, Callable, Mapping

from ..interfaces import IEventBus

Handler = Callable[[Mapping[str, Any]], None]


class EventBus(IEventBus):
    """Topic-based fan-out. Handlers must be fast; slow work goes to Telemetry pool."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._lock = RLock()
        self._published = 0

    def publish(self, topic: str, event: Mapping[str, Any]) -> None:
        with self._lock:
            handlers = list(self._subs.get(topic, ()))
            handlers.extend(self._subs.get("*", ()))
            self._published += 1
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                # Never let a subscriber crash the kernel.
                continue

    def subscribe(self, topic: str, handler: Handler) -> None:
        with self._lock:
            if handler not in self._subs[topic]:
                self._subs[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        with self._lock:
            if handler in self._subs[topic]:
                self._subs[topic].remove(handler)

    @property
    def published_count(self) -> int:
        with self._lock:
            return self._published
