"""AWPP telemetry — event bus + optional OpenTelemetry."""

from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Any, Callable, Mapping

Handler = Callable[[Mapping[str, Any]], None]


class EventBus:
    """In-process pub/sub. Handlers must be fast."""

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


class OpenTelemetryAdapter:
    """Best-effort OTEL span exporter; no-op when disabled / missing SDK."""

    def __init__(self, *, enabled: bool = False, endpoint: str = "") -> None:
        self.enabled = enabled and bool(endpoint)
        self.endpoint = endpoint
        self._tracer = None
        if self.enabled:
            try:
                from opentelemetry import trace  # type: ignore
                from opentelemetry.sdk.trace import TracerProvider  # type: ignore

                provider = TracerProvider()
                trace.set_tracer_provider(provider)
                self._tracer = trace.get_tracer("awpp")
            except Exception:
                self.enabled = False
                self._tracer = None

    def span(self, name: str, attributes: Mapping[str, Any] | None = None) -> Any:
        if not self.enabled or self._tracer is None:
            return _NullSpan()
        return self._tracer.start_as_current_span(name, attributes=dict(attributes or {}))


class _NullSpan:
    def __enter__(self) -> _NullSpan:
        return self

    def __exit__(self, *args: object) -> None:
        return None
