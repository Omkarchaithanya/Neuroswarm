"""Linux perf / ARM PMU providers with Axion-honest fallbacks."""

from __future__ import annotations

import os
import platform
import re
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


def _target_pid() -> int | None:
    raw = (os.environ.get("NSA_PERF_PID") or os.environ.get("PERF_PID") or "").strip()
    if raw.isdigit():
        return int(raw)
    return None


def _parse_perf_stat(stderr: str) -> dict[str, float]:
    out: dict[str, float] = {}
    patterns = {
        "cycles": r"([\d,]+)\s+cycles",
        "instructions": r"([\d,]+)\s+instructions",
        "cache_misses": r"([\d,]+)\s+cache-misses",
        "branch_misses": r"([\d,]+)\s+branch-misses",
    }
    for key, pat in patterns.items():
        m = re.search(pat, stderr, re.I)
        if m:
            try:
                out[key] = float(m.group(1).replace(",", ""))
            except ValueError:
                pass
    return out


class LinuxPerfProvider(ObservationProvider):
    name = "linux_perf"

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled
        self._last: dict[str, float] = {}

    def collect(self, window: TimeWindow) -> list[RawObservation]:
        metrics: dict[str, float] = {"perf_available": 0.0}
        if self.enabled and platform.system() == "Linux":
            try:
                # Soft availability probe — never fail CI if perf missing.
                result = subprocess.run(
                    ["perf", "stat", "-e", "cycles", "--", "true"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                metrics["perf_available"] = 1.0 if result.returncode == 0 else 0.0
            except Exception:
                metrics["perf_available"] = 0.0

            # Short PID-scoped sample when NSA_PERF_PID is set (live llama-server).
            pid = _target_pid()
            if metrics["perf_available"] > 0 and pid is not None:
                try:
                    duration_s = max(
                        0.1,
                        min(2.0, float((window.end - window.start).total_seconds()) or 0.5),
                    )
                except Exception:
                    duration_s = 0.5
                try:
                    sample = subprocess.run(
                        [
                            "perf",
                            "stat",
                            "-e",
                            "cycles,instructions,cache-misses,branch-misses",
                            "-p",
                            str(pid),
                            "--",
                            "sleep",
                            f"{duration_s:.3f}",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=duration_s + 5.0,
                        check=False,
                    )
                    parsed = _parse_perf_stat(sample.stderr or "")
                    cycles = float(parsed.get("cycles") or 0.0)
                    instr = float(parsed.get("instructions") or 0.0)
                    metrics.update(
                        {
                            "cycles": cycles,
                            "instructions": instr,
                            "ipc": (instr / cycles) if cycles > 0 else 0.0,
                            "cache_misses": float(parsed.get("cache_misses") or 0.0),
                            "branch_misses": float(parsed.get("branch_misses") or 0.0),
                            "target_pid": float(pid),
                        }
                    )
                except Exception:
                    metrics["sample_error"] = 1.0

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
        if not available:
            # Also accept versioned PMU device names.
            parent = Path("/sys/bus/event_source/devices")
            if parent.exists():
                available = any(p.name.startswith("armv8_pmuv3") for p in parent.iterdir())
        metrics = {
            "pmu_available": 1.0 if available else 0.0,
            "branch_misses": 0.0,
            "cache_misses": 0.0,
            "numa_remote_access": 0.0,
            "simd_util": 0.0,
        }
        # Without privileged PMU attach we export honest availability only.
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
