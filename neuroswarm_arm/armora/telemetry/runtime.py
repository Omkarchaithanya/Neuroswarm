"""Runtime Observability Framework facade + DI factory."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping

from .config import ROFRuntimeConfig, load_rof_config
from .context import RuntimeTraceContext, get_current_context, set_current_context
from .events import EventBus
from .lifecycle import ExportLifecycle, configure_meter_provider
from .logging import StructuredLogger
from .metrics import ROFMeter
from .plugins import ROFPluginRegistry
from .registry import ROFRegistry
from .schemas import EventSeverity, EventType, SpanRecord
from .spans import SpanHelper
from .tracing import ROFTracer


@dataclass
class RuntimeObservabilityFramework:
    """ARMORA-owned observability OS — traces, metrics, logs, events."""

    config: ROFRuntimeConfig
    meter: ROFMeter
    tracer: ROFTracer
    logger: StructuredLogger
    events: EventBus
    registry: ROFRegistry
    lifecycle: ExportLifecycle
    plugin_registry: ROFPluginRegistry
    spans: SpanHelper = field(init=False)
    _started: bool = False

    def __post_init__(self) -> None:
        self.spans = SpanHelper(self)

    def start(self) -> None:
        if self._started or not self.config.enabled:
            return
        self.lifecycle.start()
        # Bind OTel tracer after provider bootstrap
        try:
            from opentelemetry import trace

            self.tracer.bind_otel_tracer(trace.get_tracer("nexus.armora.rof"))
        except Exception:
            pass
        for exp in self.lifecycle.exporters:
            if getattr(exp, "name", "") == "prometheus" and hasattr(exp, "bind_meter"):
                exp.bind_meter(self.meter)
        self.registry.set_exporters(self.lifecycle.exporters)
        self._started = True

    @contextmanager
    def start_request(
        self,
        *,
        request_id: str = "",
        agent_id: str = "",
        workflow_id: str = "",
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[tuple[RuntimeTraceContext, Any]]:
        if not self.config.enabled:
            ctx = RuntimeTraceContext(request_id=request_id, agent_id=agent_id, workflow_id=workflow_id)
            token = set_current_context(ctx)
            try:
                yield ctx, None
            finally:
                from .context import reset_current_context

                reset_current_context(token)
            return
        with self.tracer.start_request(
            request_id=request_id,
            agent_id=agent_id,
            workflow_id=workflow_id,
            attributes=attributes,
        ) as pair:
            self.meter.counter("nexus_requests_total", 1.0, labels={"outcome": "started"})
            yield pair

    @contextmanager
    def span(
        self,
        name: str,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[Any]:
        if not self.config.enabled:
            yield None
            return
        with self.tracer.start_span(name, attributes=attributes) as active:
            yield active

    def counter(self, name: str, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        self.meter.counter(name, value, labels=labels)

    def gauge(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        self.meter.gauge(name, value, labels=labels)

    def histogram(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        self.meter.histogram(name, value, labels=labels)

    def log(self, level: str, message: str, **kwargs: Any) -> None:
        self.logger.log(level, message, extra=kwargs or None)

    def emit(
        self,
        event_type: str,
        *,
        payload: Mapping[str, Any] | None = None,
        severity: str = "info",
    ) -> None:
        self.events.emit(event_type, payload=payload, severity=severity)
        self.meter.counter("rof_events_emitted_total", 1.0, labels={"subsystem": "rof"})

    def emit_builtin(self, event_type: EventType, *, payload: Mapping[str, Any] | None = None) -> None:
        sev = EventSeverity.ERROR if event_type in {
            EventType.BUDGET_EXCEEDED,
            EventType.BACKEND_FAILURE,
        } else EventSeverity.INFO
        self.events.emit_builtin(event_type, payload=payload, severity=sev)
        self.meter.counter("rof_events_emitted_total", 1.0, labels={"subsystem": "rof"})

    def export_prometheus(self) -> str:
        base = self.meter.export_prometheus()
        extra = self.registry.collect_prometheus()
        return base + extra

    def register_metric_source(self, source: Any) -> None:
        self.registry.register_metric_source(source)

    def current_context(self) -> RuntimeTraceContext | None:
        return get_current_context()

    def shutdown(self, timeout_ms: int = 5000) -> None:
        self.lifecycle.shutdown(timeout_ms=timeout_ms)
        self._started = False


_ACTIVE_ROF: RuntimeObservabilityFramework | None = None


def get_rof() -> RuntimeObservabilityFramework | None:
    """Process-global ROF set by build_rof (composition root)."""
    return _ACTIVE_ROF


def build_rof(config: ROFRuntimeConfig | None = None) -> RuntimeObservabilityFramework:
    """Composition-root factory for ROF."""
    global _ACTIVE_ROF
    cfg = config or load_rof_config()
    cfg.work_dir.mkdir(parents=True, exist_ok=True)
    plugin_registry = ROFPluginRegistry(cfg)
    meter = ROFMeter()
    registry = ROFRegistry()
    exporters = plugin_registry.build_exporters()
    sampler = plugin_registry.build_sampler()

    lifecycle = ExportLifecycle(config=cfg, exporters=exporters, meter=meter)

    def _on_span_end(record: SpanRecord) -> None:
        processed = registry.process_span_end(record)
        lifecycle.enqueue_span(processed)

    tracer = ROFTracer(sampler=sampler, on_span_end=_on_span_end, enabled=cfg.enabled)

    def _on_log(record: Any) -> None:
        meter.counter("rof_logs_emitted_total", 1.0)
        lifecycle.enqueue_log(record)

    structured = StructuredLogger(level=cfg.log_level, on_log=_on_log)

    def _on_event(event: Any) -> None:
        lifecycle.enqueue_event(event)

    bus = EventBus(on_emit=_on_event)

    configure_meter_provider(cfg)

    rof = RuntimeObservabilityFramework(
        config=cfg,
        meter=meter,
        tracer=tracer,
        logger=structured,
        events=bus,
        registry=registry,
        lifecycle=lifecycle,
        plugin_registry=plugin_registry,
    )
    if cfg.enabled:
        rof.start()
    _ACTIVE_ROF = rof
    return rof
