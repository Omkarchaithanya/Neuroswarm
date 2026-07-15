"""Runtime metrics ObservationProvider (ASCR/HAOE/RTG/router/MAKS hooks)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from neuroswarm_arm.evolution.interfaces.observation import ObservationProvider
from neuroswarm_arm.evolution.models.observation import (
    HealthStatus,
    ObservationSnapshot,
    RawObservation,
    TimeWindow,
)


class RuntimeObservationProvider(ObservationProvider):
    name = "runtime"

    def __init__(
        self,
        *,
        metrics_fn: Callable[[], dict[str, float]] | None = None,
        haoe_snapshot: Path | None = None,
        sink: list[dict[str, float]] | None = None,
    ) -> None:
        self.metrics_fn = metrics_fn
        self.haoe_snapshot = haoe_snapshot or Path("work/haoe/performix_snapshot.json")
        self.sink = sink if sink is not None else []
        self._last: dict[str, float] = {}

    def record(self, metrics: dict[str, float]) -> None:
        """In-process sink compatible with ASCR PerformixHook.record style."""
        cleaned = {k: float(v) for k, v in metrics.items()}
        self.sink.append(cleaned)
        if len(self.sink) > 1000:
            del self.sink[: len(self.sink) - 1000]
        self._last = cleaned

    def collect(self, window: TimeWindow) -> list[RawObservation]:
        now = datetime.now(timezone.utc)
        events: list[RawObservation] = []
        if self.metrics_fn:
            try:
                m = self.metrics_fn()
                events.append(
                    RawObservation(source=self.name, collected_at=now, metrics={k: float(v) for k, v in m.items()})
                )
            except Exception:
                pass
        for item in list(self.sink)[-50:]:
            events.append(RawObservation(source=f"{self.name}.sink", collected_at=now, metrics=dict(item)))
        if self.haoe_snapshot.exists():
            try:
                data = json.loads(self.haoe_snapshot.read_text(encoding="utf-8"))
                metrics: dict[str, float] = {}
                if isinstance(data, dict):
                    for k, v in data.items():
                        try:
                            metrics[f"haoe_{k}"] = float(v)
                        except (TypeError, ValueError):
                            continue
                if metrics:
                    events.append(
                        RawObservation(
                            source="haoe_snapshot",
                            collected_at=now,
                            metrics=metrics,
                            labels={"layer": "haoe"},
                        )
                    )
            except Exception:
                pass
        if not events:
            events.append(
                RawObservation(
                    source=self.name,
                    collected_at=now,
                    metrics=dict(self._last) or {"runtime_idle": 1.0},
                )
            )
        if events:
            self._last = dict(events[-1].metrics)
        return events

    def snapshot(self) -> ObservationSnapshot:
        return ObservationSnapshot(
            collected_at=datetime.now(timezone.utc),
            providers={self.name: dict(self._last)},
            aggregate=dict(self._last),
        )

    def metrics(self) -> dict[str, float]:
        if self.metrics_fn:
            try:
                return {k: float(v) for k, v in self.metrics_fn().items()}
            except Exception:
                pass
        return dict(self._last)

    def health(self) -> HealthStatus:
        return HealthStatus(healthy=True, provider=self.name, details={"sink_len": len(self.sink)})


class CustomRuntimeProvider(RuntimeObservationProvider):
    name = "custom_runtime"
