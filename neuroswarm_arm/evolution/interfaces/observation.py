"""ObservationProvider port — Performix is one backend, not the optimizer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from typing import Any, Protocol, runtime_checkable

from neuroswarm_arm.evolution.models.observation import (
    HealthStatus,
    ObservationSnapshot,
    ObservationSummary,
    RawObservation,
    TimeWindow,
)


@runtime_checkable
class ExportSink(Protocol):
    def export_metrics(self, metrics: dict[str, float], *, labels: dict[str, str] | None = None) -> None: ...


class ObservationProvider(ABC):
    """Collect / stream / snapshot runtime and hardware observations."""

    name: str = "base"

    @abstractmethod
    def collect(self, window: TimeWindow) -> list[RawObservation]:
        raise NotImplementedError

    def stream(self) -> Iterator[RawObservation]:
        """Sync stream default: one-shot collect over last 60s."""
        for obs in self.collect(TimeWindow.last_seconds(60)):
            yield obs

    async def astream(self) -> AsyncIterator[RawObservation]:
        for obs in self.stream():
            yield obs

    @abstractmethod
    def snapshot(self) -> ObservationSnapshot:
        raise NotImplementedError

    @abstractmethod
    def metrics(self) -> dict[str, float]:
        raise NotImplementedError

    def summarize(self, window: TimeWindow | None = None) -> ObservationSummary:
        w = window or TimeWindow.last_seconds(300)
        events = self.collect(w)
        means: dict[str, float] = {}
        counts: dict[str, int] = {}
        for ev in events:
            for k, v in ev.metrics.items():
                means[k] = means.get(k, 0.0) + float(v)
                counts[k] = counts.get(k, 0) + 1
        for k in list(means):
            means[k] = means[k] / max(counts[k], 1)
        return ObservationSummary(window=w, n_events=len(events), means=means)

    @abstractmethod
    def health(self) -> HealthStatus:
        raise NotImplementedError

    def export(self, sink: ExportSink) -> None:
        sink.export_metrics(self.metrics(), labels={"provider": self.name})
