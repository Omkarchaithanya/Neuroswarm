"""OpenTelemetry / Prometheus export ObservationProviders (stubs safe for CI)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from neuroswarm_arm.evolution.interfaces.observation import ExportSink, ObservationProvider
from neuroswarm_arm.evolution.models.observation import (
    HealthStatus,
    ObservationSnapshot,
    RawObservation,
    TimeWindow,
)


class InMemoryExportSink:
    def __init__(self) -> None:
        self.series: list[tuple[dict[str, float], dict[str, str]]] = []

    def export_metrics(self, metrics: dict[str, float], *, labels: dict[str, str] | None = None) -> None:
        self.series.append((dict(metrics), dict(labels or {})))


class PrometheusObservationProvider(ObservationProvider):
    """Reads from a callable that returns Prometheus-style gauge map."""

    name = "prometheus"

    def __init__(self, scrape_fn: Callable[[], dict[str, float]] | None = None) -> None:
        self.scrape_fn = scrape_fn or (lambda: {})
        self._last: dict[str, float] = {}
        self._export_buffer: list[str] = []

    def collect(self, window: TimeWindow) -> list[RawObservation]:
        try:
            self._last = {k: float(v) for k, v in self.scrape_fn().items()}
        except Exception:
            self._last = {}
        return [
            RawObservation(
                source=self.name,
                collected_at=datetime.now(timezone.utc),
                metrics=dict(self._last),
            )
        ]

    def snapshot(self) -> ObservationSnapshot:
        return ObservationSnapshot(
            collected_at=datetime.now(timezone.utc),
            providers={self.name: dict(self._last)},
            aggregate=dict(self._last),
        )

    def metrics(self) -> dict[str, float]:
        return dict(self._last)

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=True, provider=self.name, details={"n_metrics": len(self._last)})

    def prometheus_text(self, metrics: dict[str, float] | None = None) -> str:
        m = metrics if metrics is not None else self.metrics()
        lines = ["# HELP arop_metric AROP aggregated metric", "# TYPE arop_metric gauge"]
        for k, v in sorted(m.items()):
            safe = k.replace("-", "_").replace(".", "_")
            lines.append(f'arop_metric{{name="{safe}"}} {float(v)}')
        text = "\n".join(lines) + "\n"
        self._export_buffer.append(text)
        return text

    def export(self, sink: ExportSink) -> None:
        sink.export_metrics(self.metrics(), labels={"provider": self.name})


class OpenTelemetryProvider(ObservationProvider):
    name = "otel"

    def __init__(self) -> None:
        self._last: dict[str, float] = {}
        self._spans: list[dict[str, float]] = []

    def record_span_metrics(self, metrics: dict[str, float]) -> None:
        cleaned = {k: float(v) for k, v in metrics.items()}
        self._spans.append(cleaned)
        self._last = cleaned

    def collect(self, window: TimeWindow) -> list[RawObservation]:
        now = datetime.now(timezone.utc)
        if not self._spans:
            return [RawObservation(source=self.name, collected_at=now, metrics={"otel_idle": 1.0})]
        return [
            RawObservation(source=self.name, collected_at=now, metrics=dict(s))
            for s in self._spans[-20:]
        ]

    def snapshot(self) -> ObservationSnapshot:
        return ObservationSnapshot(
            collected_at=datetime.now(timezone.utc),
            providers={self.name: dict(self._last)},
            aggregate=dict(self._last),
        )

    def metrics(self) -> dict[str, float]:
        return dict(self._last)

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=True, provider=self.name, details={"spans": len(self._spans)})
