"""AROP ObservationProvider — read-only RPF history as GEPA ASI."""

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


class ProfilingObservationProvider(ObservationProvider):
    """Expose RuntimeProfile aggregates to AROP without mutating planner or envelopes."""

    name = "rpf"

    def __init__(self, rpf: Any) -> None:
        self.rpf = rpf

    def collect(self, window: TimeWindow) -> list[RawObservation]:
        out: list[RawObservation] = []
        try:
            profiles = self.rpf.store.query(limit=self.rpf.config.history_window)
        except Exception:
            return out
        for profile in profiles:
            try:
                ts = datetime.fromisoformat(profile.created_at.replace("Z", "+00:00"))
            except Exception:
                ts = datetime.now(timezone.utc)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts < window.start or ts > window.end:
                continue
            metrics = {
                "cpu_percent": float(profile.cpu.usage_percent),
                "wall_ms": float(profile.cpu.wall_time_ms),
                "rss_bytes": float(profile.memory.rss_bytes),
                "ipc": float(profile.hardware.ipc or profile.hardware.derived_ipc),
                "cache_misses": float(profile.hardware.cache_misses),
                "execution_ms": float(profile.execution.execution_time_ms),
                "planner_ms": float(profile.planner.planner_time_ms),
                "spec_accept": float(profile.execution.speculative_acceptance_ratio),
            }
            out.append(
                RawObservation(
                    source=self.name,
                    collected_at=ts,
                    metrics=metrics,
                    labels={
                        "profiler": profile.profiler_used,
                        "backend": profile.backend.backend,
                        "agent_id": profile.agent_id,
                        "workflow_id": profile.workflow_id,
                    },
                    payload={
                        "profile_id": profile.profile_id,
                        "execution_id": profile.execution_id,
                        "recommendations": list(profile.recommendations),
                        "asi": self.rpf.feedback.observation_vector(profile),
                    },
                )
            )
        return out

    def snapshot(self) -> ObservationSnapshot:
        try:
            profiles = self.rpf.store.query(limit=20)
        except Exception:
            profiles = []
        aggregate: dict[str, float] = {}
        if profiles:
            aggregate = {
                "cpu_percent": sum(p.cpu.usage_percent for p in profiles) / len(profiles),
                "ipc": sum((p.hardware.ipc or 0.0) for p in profiles) / len(profiles),
                "execution_ms": sum(p.execution.execution_time_ms for p in profiles)
                / len(profiles),
            }
        return ObservationSnapshot(
            collected_at=datetime.now(timezone.utc),
            providers={self.name: dict(aggregate)},
            aggregate=dict(aggregate),
        )

    def metrics(self) -> dict[str, float]:
        snap = self.snapshot()
        return dict(snap.aggregate)

    def health(self) -> HealthStatus:
        try:
            h = self.rpf.health()
            return HealthStatus(
                healthy=bool(h.get("healthy", True)),
                provider=self.name,
                details=dict(h) if isinstance(h, dict) else {},
            )
        except Exception as exc:
            return HealthStatus(
                healthy=False,
                provider=self.name,
                details={"error": str(exc)},
            )
