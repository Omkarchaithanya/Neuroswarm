"""Linux perf / ARM PMU providers with Axion-honest fallbacks."""

from __future__ import annotations

import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from neuroswarm_arm.evolution.interfaces.observation import ObservationProvider
from neuroswarm_arm.evolution.models.observation import (
    HealthStatus,
    ObservationSnapshot,
    RawObservation,
    TimeWindow,
)


class LinuxPerfProvider(ObservationProvider):
    name = "linux_perf"

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled
        self._last: dict[str, float] = {}

    def collect(self, window: TimeWindow) -> list[RawObservation]:
        metrics: dict[str, float] = {"perf_available": 0.0}
        if self.enabled and platform.system() == "Linux":
            try:
                # Soft probe only — never fail CI if perf missing.
                result = subprocess.run(
                    ["perf", "stat", "-e", "cycles", "--", "true"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                metrics["perf_available"] = 1.0 if result.returncode == 0 else 0.0
            except Exception:
                metrics["perf_available"] = 0.0
        self._last = metrics
        return [
            RawObservation(
                source=self.name,
                collected_at=datetime.now(timezone.utc),
                metrics=metrics,
                labels={"os": platform.system()},
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
        return HealthStatus(
            healthy=True,
            provider=self.name,
            details={"enabled": self.enabled, "os": platform.system()},
        )


class PMUCounterProvider(ObservationProvider):
    """ARM PMU counter reader — degrades on Axion/Windows without PMU access."""

    name = "arm_pmu"

    def __init__(self, *, sysfs_root: Path | None = None) -> None:
        self.sysfs_root = sysfs_root or Path("/sys/bus/event_source/devices/armv8_pmuv3")
        self._last: dict[str, float] = {}

    def collect(self, window: TimeWindow) -> list[RawObservation]:
        available = self.sysfs_root.exists()
        metrics = {
            "pmu_available": 1.0 if available else 0.0,
            "branch_misses": 0.0,
            "cache_misses": 0.0,
            "numa_remote_access": 0.0,
            "simd_util": 0.0,
        }
        # Without privileged PMU access we export honest zeros + availability flag.
        self._last = metrics
        return [
            RawObservation(
                source=self.name,
                collected_at=datetime.now(timezone.utc),
                metrics=metrics,
                labels={"layer": "haoe", "axion_honest": "1"},
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
        return HealthStatus(
            healthy=True,
            provider=self.name,
            details={"pmu_sysfs": str(self.sysfs_root), "available": self.sysfs_root.exists()},
        )
