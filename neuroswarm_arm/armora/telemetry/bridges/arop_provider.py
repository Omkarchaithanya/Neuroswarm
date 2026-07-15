"""AROP ObservationProvider — read-only ROF metrics as Plane-5 ASI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from neuroswarm_arm.evolution.interfaces.observation import ObservationProvider
from neuroswarm_arm.evolution.models.observation import (
    HealthStatus,
    ObservationSnapshot,
    RawObservation,
    TimeWindow,
)


class ROFObservationProvider(ObservationProvider):
    """Expose ROF meter snapshot to AROP without mutating traces or budgets."""

    name = "rof"

    def __init__(self, rof: Any) -> None:
        self.rof = rof
        self._history: list[RawObservation] = []

    def collect(self, window: TimeWindow) -> list[RawObservation]:
        now = datetime.now(timezone.utc)
        snap = self.snapshot()
        obs = RawObservation(
            source=self.name,
            collected_at=now,
            metrics=dict(snap.aggregate),
            labels={"provider": self.name},
            payload={"service": self.rof.config.service_name},
        )
        self._history.append(obs)
        if len(self._history) > 256:
            self._history = self._history[-128:]
        return [o for o in self._history if window.start <= o.collected_at <= window.end]

    def snapshot(self) -> ObservationSnapshot:
        metrics = self.metrics()
        return ObservationSnapshot(
            collected_at=datetime.now(timezone.utc),
            providers={self.name: metrics},
            aggregate=metrics,
        )

    def metrics(self) -> dict[str, float]:
        snap = self.rof.meter.snapshot()
        out: dict[str, float] = {}
        for key, value in snap.items():
            base = key.split("{", 1)[0]
            if base.startswith(("rof_", "nexus_")):
                out[base] = float(value)
        return out

    def health(self) -> HealthStatus:
        enabled = bool(self.rof.config.enabled)
        started = bool(getattr(self.rof, "_started", False))
        return HealthStatus(
            healthy=enabled,
            provider=self.name,
            details={
                "enabled": enabled,
                "started": started,
                "exporters": list(self.rof.config.exporters),
                "sampler": self.rof.config.sampler,
            },
        )
