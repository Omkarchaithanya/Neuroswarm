"""ROF lifecycle — single provider bootstrap, batch export, graceful shutdown."""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any

from .config import ROFRuntimeConfig
from .schemas import LogRecord, MetricSample, RuntimeEvent, SpanRecord

logger = logging.getLogger(__name__)


class ExportLifecycle:
    """Background batch export with backpressure and dropped-span accounting."""

    def __init__(
        self,
        *,
        config: ROFRuntimeConfig,
        exporters: list[Any],
        meter: Any,
    ) -> None:
        self.config = config
        self.exporters = list(exporters)
        self.meter = meter
        self._span_q: queue.Queue[SpanRecord | None] = queue.Queue(maxsize=config.max_queue_size)
        self._log_q: queue.Queue[LogRecord | None] = queue.Queue(maxsize=config.max_queue_size)
        self._event_q: queue.Queue[RuntimeEvent | None] = queue.Queue(maxsize=config.max_queue_size)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._otel_ready = False

    def start(self) -> None:
        self._bootstrap_otel()
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="rof-export", daemon=True)
        self._thread.start()

    def _bootstrap_otel(self) -> None:
        if self._otel_ready or not self.config.enabled:
            return
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider

            resource = Resource.create(
                {
                    "service.name": self.config.service_name,
                    "service.version": self.config.service_version,
                }
            )
            provider = trace.get_tracer_provider()
            if type(provider).__name__ == "ProxyTracerProvider":
                provider = TracerProvider(resource=resource)
                trace.set_tracer_provider(provider)
            self._otel_ready = True
        except Exception as exc:
            logger.debug("ROF OTel bootstrap skipped: %s", exc)

    def enqueue_span(self, span: SpanRecord) -> None:
        try:
            self._span_q.put_nowait(span)
        except queue.Full:
            self.meter.counter("rof_spans_dropped_total", 1.0, labels={"exporter": "queue"})

    def enqueue_log(self, record: LogRecord) -> None:
        try:
            self._log_q.put_nowait(record)
        except queue.Full:
            self.meter.counter("rof_spans_dropped_total", 1.0, labels={"exporter": "log_queue"})

    def enqueue_event(self, event: RuntimeEvent) -> None:
        try:
            self._event_q.put_nowait(event)
        except queue.Full:
            pass

    def _drain(self, q: queue.Queue[Any], limit: int) -> list[Any]:
        items: list[Any] = []
        while len(items) < limit:
            try:
                item = q.get_nowait()
            except queue.Empty:
                break
            if item is None:
                break
            items.append(item)
        return items

    def _export_batch(self) -> None:
        spans = self._drain(self._span_q, self.config.batch_size)
        logs = self._drain(self._log_q, self.config.batch_size)
        events = self._drain(self._event_q, self.config.batch_size)
        if not spans and not logs and not events:
            return
        t0 = time.perf_counter()
        for exp in self.exporters:
            try:
                if spans and hasattr(exp, "export_spans"):
                    n = exp.export_spans(spans)
                    if n:
                        self.meter.counter(
                            "rof_spans_exported_total",
                            float(n),
                            labels={"exporter": getattr(exp, "name", "unknown")},
                        )
                if logs and hasattr(exp, "export_logs"):
                    exp.export_logs(logs)
                if events and hasattr(exp, "sink_event"):
                    for ev in events:
                        exp.sink_event(ev)
            except Exception:
                self.meter.counter(
                    "rof_export_failures_total",
                    1.0,
                    labels={"exporter": getattr(exp, "name", "unknown")},
                )
        self.meter.gauge("rof_export_latency_seconds", time.perf_counter() - t0)

    def _run(self) -> None:
        interval = max(0.05, self.config.export_interval_ms / 1000.0)
        while not self._stop.is_set():
            try:
                self._export_batch()
            except Exception as exc:
                logger.debug("ROF export loop error: %s", exc)
            self._stop.wait(interval)
        # Final flush
        try:
            self._export_batch()
        except Exception:
            pass

    def shutdown(self, timeout_ms: int = 5000) -> None:
        self._stop.set()
        try:
            self._span_q.put_nowait(None)
        except queue.Full:
            pass
        if self._thread is not None:
            self._thread.join(timeout=max(0.1, timeout_ms / 1000.0))
        for exp in self.exporters:
            try:
                exp.shutdown(timeout_ms=timeout_ms)
            except Exception:
                pass


def configure_meter_provider(config: ROFRuntimeConfig) -> None:
    """Best-effort MeterProvider bootstrap for OTel metrics."""
    try:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": config.service_name})
        provider = metrics.get_meter_provider()
        if type(provider).__name__ == "ProxyMeterProvider":
            metrics.set_meter_provider(MeterProvider(resource=resource))
    except Exception:
        pass
