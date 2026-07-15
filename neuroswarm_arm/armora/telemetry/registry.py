"""ROF component registry — metric sources, processors, dashboard providers."""

from __future__ import annotations

import threading
from typing import Any

from .ports import IDashboardProvider, IMetricSource, ITraceProcessor


class ROFRegistry:
    """Runtime registry for pluggable ROF components."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.metric_sources: dict[str, IMetricSource] = {}
        self.trace_processors: dict[str, ITraceProcessor] = {}
        self.dashboard_providers: dict[str, IDashboardProvider] = {}
        self.exporters: list[Any] = []

    def register_metric_source(self, source: IMetricSource) -> None:
        with self._lock:
            self.metric_sources[source.name] = source

    def unregister_metric_source(self, name: str) -> None:
        with self._lock:
            self.metric_sources.pop(name, None)

    def register_trace_processor(self, processor: ITraceProcessor) -> None:
        with self._lock:
            self.trace_processors[processor.name] = processor

    def register_dashboard_provider(self, provider: IDashboardProvider) -> None:
        with self._lock:
            self.dashboard_providers[provider.name] = provider

    def set_exporters(self, exporters: list[Any]) -> None:
        with self._lock:
            self.exporters = list(exporters)

    def collect_prometheus(self) -> str:
        chunks: list[str] = []
        with self._lock:
            sources = list(self.metric_sources.values())
            exporters = list(self.exporters)
        for source in sources:
            try:
                text = source.export_prometheus()
                if text:
                    chunks.append(text if text.endswith("\n") else text + "\n")
            except Exception:
                continue
        for exp in exporters:
            if hasattr(exp, "export_prometheus"):
                try:
                    text = exp.export_prometheus()
                    if text:
                        chunks.append(text if text.endswith("\n") else text + "\n")
                except Exception:
                    continue
        return "".join(chunks)

    def process_span_start(self, span: Any) -> Any:
        with self._lock:
            processors = list(self.trace_processors.values())
        for proc in processors:
            try:
                span = proc.on_start(span)
            except Exception:
                continue
        return span

    def process_span_end(self, span: Any) -> Any:
        with self._lock:
            processors = list(self.trace_processors.values())
        for proc in processors:
            try:
                span = proc.on_end(span)
            except Exception:
                continue
        return span
