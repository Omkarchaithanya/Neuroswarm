"""Ports / Protocols for hexagonal Runtime Observability Framework."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Iterator, Mapping, Protocol, runtime_checkable

from .schemas import LogRecord, MetricSample, RuntimeEvent, SamplingDecision, SpanRecord


@runtime_checkable
class ISampler(Protocol):
    name: str

    def should_sample(
        self,
        *,
        name: str,
        attributes: Mapping[str, Any] | None = None,
        parent_sampled: bool | None = None,
    ) -> SamplingDecision: ...


@runtime_checkable
class ITracer(Protocol):
    def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, Any] | None = None,
        parent: Any | None = None,
    ) -> AbstractContextManager[Any]: ...


@runtime_checkable
class IMeter(Protocol):
    def counter(self, name: str, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None: ...

    def gauge(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None: ...

    def histogram(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None: ...

    def describe(self, name: str, metric_type: str, help_text: str) -> None: ...

    def export_prometheus(self) -> str: ...


@runtime_checkable
class IStructuredLogger(Protocol):
    def log(
        self,
        level: str,
        message: str,
        *,
        extra: Mapping[str, Any] | None = None,
    ) -> None: ...

    def info(self, message: str, **kwargs: Any) -> None: ...

    def warning(self, message: str, **kwargs: Any) -> None: ...

    def error(self, message: str, **kwargs: Any) -> None: ...


@runtime_checkable
class IEventBus(Protocol):
    def emit(self, event: RuntimeEvent) -> None: ...

    def subscribe(self, event_type: str, handler: Any) -> None: ...

    def unsubscribe(self, event_type: str, handler: Any) -> None: ...


@runtime_checkable
class ISpanExporter(Protocol):
    name: str

    def export_spans(self, spans: list[SpanRecord]) -> int: ...

    def shutdown(self, timeout_ms: int = 5000) -> None: ...


@runtime_checkable
class IMetricExporter(Protocol):
    name: str

    def export_metrics(self, samples: list[MetricSample]) -> int: ...

    def export_prometheus(self) -> str: ...

    def shutdown(self, timeout_ms: int = 5000) -> None: ...


@runtime_checkable
class ILogExporter(Protocol):
    name: str

    def export_logs(self, records: list[LogRecord]) -> int: ...

    def shutdown(self, timeout_ms: int = 5000) -> None: ...


@runtime_checkable
class IEventSink(Protocol):
    name: str

    def sink(self, event: RuntimeEvent) -> None: ...


@runtime_checkable
class ITraceProcessor(Protocol):
    name: str

    def on_start(self, span: SpanRecord) -> SpanRecord: ...

    def on_end(self, span: SpanRecord) -> SpanRecord: ...


@runtime_checkable
class IMetricSource(Protocol):
    name: str

    def collect(self) -> list[MetricSample]: ...

    def export_prometheus(self) -> str: ...


@runtime_checkable
class IDashboardProvider(Protocol):
    name: str

    def dashboard_specs(self) -> list[Mapping[str, Any]]: ...


@runtime_checkable
class IROF(Protocol):
    """Facade for the Runtime Observability Framework."""

    def start_request(
        self,
        *,
        request_id: str = "",
        agent_id: str = "",
        workflow_id: str = "",
        attributes: Mapping[str, Any] | None = None,
    ) -> AbstractContextManager[Any]: ...

    def span(
        self,
        name: str,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> AbstractContextManager[Any]: ...

    def counter(self, name: str, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None: ...

    def gauge(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None: ...

    def histogram(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None: ...

    def log(self, level: str, message: str, **kwargs: Any) -> None: ...

    def emit(self, event_type: str, *, payload: Mapping[str, Any] | None = None, severity: str = "info") -> None: ...

    def export_prometheus(self) -> str: ...

    def register_metric_source(self, source: IMetricSource) -> None: ...

    def shutdown(self, timeout_ms: int = 5000) -> None: ...
