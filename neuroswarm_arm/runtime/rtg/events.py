"""In-process RTG event bus."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Callable


Listener = Callable[[dict[str, Any]], None]


class EventBus:
    """Thread-safe pub/sub for rtg.* topics."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._listeners: dict[str, list[Listener]] = defaultdict(list)

    def subscribe(self, topic: str, listener: Listener) -> None:
        with self._lock:
            self._listeners[topic].append(listener)

    def publish(self, topic: str, payload: dict[str, Any] | None = None) -> None:
        data = dict(payload or {})
        data.setdefault("topic", topic)
        with self._lock:
            listeners = list(self._listeners.get(topic, []))
            listeners.extend(self._listeners.get("*", []))
        for fn in listeners:
            try:
                fn(data)
            except Exception:  # noqa: BLE001 — never break control path
                continue
