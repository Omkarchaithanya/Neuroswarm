"""ARM PMU hooks — best-effort counters (Axion-safe no-op)."""

from __future__ import annotations

import os
from typing import Any


class ArmPMU:
    """Best-effort performance monitoring unit access."""

    def __init__(self) -> None:
        self.available = False
        self._counters: dict[str, float] = {}
        self._probe()

    def _probe(self) -> None:
        # Cloud VMs often lack perf_event; keep disabled unless explicitly enabled.
        if os.getenv("NSA_ARM_PMU", "0") not in {"1", "true", "True"}:
            return
        # Soft availability: loadavg / cpu count as proxy when real PMU absent.
        self.available = True
        try:
            if hasattr(os, "getloadavg"):
                load1 = float(os.getloadavg()[0])
                cpus = float(os.cpu_count() or 1)
                self._counters["cpu_utilization"] = min(1.0, load1 / cpus)
                self._counters["cycles"] = 0.0
                self._counters["instructions"] = 0.0
                self._counters["l3_miss_rate"] = 0.0
        except Exception:  # noqa: BLE001
            self.available = False

    def read(self) -> dict[str, float]:
        if self.available:
            self._probe()
        return dict(self._counters)

    def sample(self, name: str, value: float) -> None:
        self._counters[name] = float(value)
        self.available = True

    def status(self) -> dict[str, Any]:
        return {"available": self.available, "counters": self.read()}
