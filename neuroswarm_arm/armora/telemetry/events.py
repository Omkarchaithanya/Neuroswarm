"""Runtime event bus — typed events dual-published to sinks."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Callable, Mapping

from .context import get_current_context
from .schemas import EventSeverity, EventType, RuntimeEvent

Handler = Callable[[RuntimeEvent], None]


class EventBus:
    """In-process pub/sub with optional sink fan-out."""

    def __init__(self, *, on_emit: Callable[[RuntimeEvent], None] | None = None) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.Lock()
        self.on_emit = on_emit
        self._custom_types: set[str] = set()
        for et in EventType:
            if et != EventType.CUSTOM:
                self._custom_types.add(et.value)

    def register_event_type(self, name: str) -> str:
        key = name.strip()
        with self._lock:
            self._custom_types.add(key)
        return key

    def subscribe(self, event_type: str, handler: Handler) -> None:
        with self._lock:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        with self._lock:
            handlers = self._handlers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

    def emit(
        self,
        event_type: str,
        *,
        payload: Mapping[str, Any] | None = None,
        severity: str | EventSeverity = EventSeverity.INFO,
        context: Mapping[str, Any] | None = None,
    ) -> RuntimeEvent:
        sev = EventSeverity(severity) if isinstance(severity, str) else severity
        ctx = get_current_context()
        ctx_map = dict(context or {})
        if ctx is not None:
            ctx_map = {**ctx.to_log_fields(), **ctx_map}
        event = RuntimeEvent(
            event_type=event_type,
            severity=sev,
            context=ctx_map,
            payload=dict(payload or {}),
        )
        if self.on_emit is not None:
            try:
                self.on_emit(event)
            except Exception:
                pass
        with self._lock:
            handlers = list(self._handlers.get(event_type, []))
            handlers.extend(self._handlers.get("*", []))
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                pass
        return event

    def emit_builtin(
        self,
        event_type: EventType,
        *,
        payload: Mapping[str, Any] | None = None,
        severity: EventSeverity = EventSeverity.INFO,
    ) -> RuntimeEvent:
        return self.emit(event_type.value, payload=payload, severity=severity)
