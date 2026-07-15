"""Simple pub/sub event bus."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Mapping


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[Mapping[str, Any]], None]]] = defaultdict(
            list
        )

    def publish(self, topic: str, event: Mapping[str, Any]) -> None:
        for handler in list(self._subs.get(topic, [])):
            try:
                handler(event)
            except Exception:
                continue

    def subscribe(
        self, topic: str, handler: Callable[[Mapping[str, Any]], None]
    ) -> None:
        self._subs[topic].append(handler)

    def unsubscribe(
        self, topic: str, handler: Callable[[Mapping[str, Any]], None]
    ) -> None:
        handlers = self._subs.get(topic, [])
        if handler in handlers:
            handlers.remove(handler)
