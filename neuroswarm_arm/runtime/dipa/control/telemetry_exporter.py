"""TelemetryExporter — shared OTEL + Prometheus-friendly bridge."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from .metrics_collector import MetricsCollector

LOG = logging.getLogger("nexus.dipa.telemetry")


class TelemetryExporter:
    """Single provider used by DIPA control plane (and adoptable by RTG/router)."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        endpoint: str = "",
        service_name: str = "nexus-arm-dipa",
        metrics: MetricsCollector | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.service_name = service_name
        self.metrics = metrics or MetricsCollector()
        self._tracer = None
        self.enabled = bool(enabled and endpoint)
        self._init_error: str | None = None
        if self.enabled:
            self._init_otel()

    def _init_otel(self) -> None:
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider = TracerProvider(
                resource=Resource.create({"service.name": self.service_name})
            )
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=self.endpoint))
            )
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer(self.service_name)
        except Exception as exc:
            self.enabled = False
            self._tracer = None
            self._init_error = str(exc)
            LOG.warning("otel init failed: %s", exc)

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[Any]:
        self.metrics.incr("otel.spans", span=name)
        t0 = time.perf_counter()
        if not self.enabled or self._tracer is None:
            try:
                yield None
            finally:
                self.metrics.observe(
                    "otel.span_ms", (time.perf_counter() - t0) * 1000.0, span=name
                )
            return
        with self._tracer.start_as_current_span(name) as sp:
            for k, v in attrs.items():
                try:
                    sp.set_attribute(k, _attr(v))
                except Exception:
                    pass
            try:
                yield sp
            finally:
                self.metrics.observe(
                    "otel.span_ms", (time.perf_counter() - t0) * 1000.0, span=name
                )

    def event(self, name: str, **attrs: Any) -> None:
        self.metrics.incr(f"event.{name}", **{k: str(v) for k, v in attrs.items()})
        LOG.debug("telemetry event %s %s", name, attrs)

    def record_request(self, *, backend: str = "", status: str = "ok") -> None:
        self.metrics.incr("inference.request", backend=backend, status=status)

    def record_token(self, n: int = 1, *, backend: str = "") -> None:
        self.metrics.incr("inference.tokens", n, backend=backend)

    def record_model_load(self, model_ref: str, *, ok: bool = True) -> None:
        self.metrics.incr("inference.model_load", model=model_ref, ok=str(ok))

    def record_kv_alloc(self, *, hit: bool = False) -> None:
        self.metrics.incr("inference.kv_alloc", hit=str(hit))

    def record_queue(self, wait_ms: float) -> None:
        self.metrics.observe("inference.queue_wait_ms", wait_ms)

    def record_warmup(self, *, ok: bool = True) -> None:
        self.metrics.incr("inference.warmup", ok=str(ok))

    def record_cancel(self) -> None:
        self.metrics.incr("inference.cancel")

    def record_timeout(self) -> None:
        self.metrics.incr("inference.timeout")

    def record_retry(self) -> None:
        self.metrics.incr("inference.retry")

    def snapshot(self) -> Mapping[str, Any]:
        return {
            "enabled": self.enabled,
            "endpoint": self.endpoint,
            "service_name": self.service_name,
            "init_error": self._init_error,
            "metrics": self.metrics.snapshot(),
        }


def _attr(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
