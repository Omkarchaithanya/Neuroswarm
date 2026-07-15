"""Trace / span helpers for RPF — best-effort OTel bridge."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator, Mapping
from uuid import uuid4

logger = logging.getLogger(__name__)


class TraceRecorder:
    """In-process span recorder with optional OpenTelemetry export."""

    def __init__(self, *, otel_enabled: bool = False) -> None:
        self._spans: dict[str, dict[str, Any]] = {}
        self._tracer = None
        if otel_enabled:
            try:
                from opentelemetry import trace  # type: ignore

                self._tracer = trace.get_tracer("nexus.armora.rpf")
            except Exception:
                self._tracer = None

    def start_span(self, name: str, *, attributes: Mapping[str, Any] | None = None) -> str:
        span_id = str(uuid4())
        self._spans[span_id] = {
            "name": name,
            "attributes": dict(attributes or {}),
            "otel": None,
        }
        if self._tracer is not None:
            try:
                otel_span = self._tracer.start_span(name)
                for k, v in (attributes or {}).items():
                    try:
                        otel_span.set_attribute(str(k), v)
                    except Exception:
                        pass
                self._spans[span_id]["otel"] = otel_span
            except Exception as exc:
                logger.debug("rpf otel start_span failed: %s", exc)
        return span_id

    def end_span(self, span_id: str) -> None:
        info = self._spans.pop(span_id, None)
        if info is None:
            return
        otel_span = info.get("otel")
        if otel_span is not None:
            try:
                otel_span.end()
            except Exception:
                pass

    @contextmanager
    def span(self, name: str, *, attributes: Mapping[str, Any] | None = None) -> Iterator[str]:
        span_id = self.start_span(name, attributes=attributes)
        try:
            yield span_id
        finally:
            self.end_span(span_id)

    def active_count(self) -> int:
        return len(self._spans)
