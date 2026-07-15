"""Local metrics collector for Agent Registry (OTel-ready names)."""

from __future__ import annotations

import threading
from typing import Any, Mapping


class RegistryMetrics:
    """Thread-safe counters / gauges for registry operations."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._labeled: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

    def inc(self, name: str, value: float = 1.0, *, labels: Mapping[str, str] | None = None) -> None:
        with self._lock:
            if labels:
                key = (name, tuple(sorted(labels.items())))
                self._labeled[key] = self._labeled.get(key, 0.0) + value
            else:
                self._counters[name] = self._counters.get(name, 0.0) + value

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def observe(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        """Record a sample as a running sum + count for averages."""
        self.inc(f"{name}_sum", value, labels=labels)
        self.inc(f"{name}_count", 1.0, labels=labels)

    def get(self, name: str) -> float:
        with self._lock:
            return float(self._counters.get(name, self._gauges.get(name, 0.0)))

    def average(self, name: str) -> float:
        with self._lock:
            total = self._counters.get(f"{name}_sum", 0.0)
            count = self._counters.get(f"{name}_count", 0.0)
            return float(total / count) if count else 0.0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            labeled = {
                f"{n}|{','.join(f'{k}={v}' for k, v in labs)}": val
                for (n, labs), val in self._labeled.items()
            }
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "labeled": labeled,
                "avg_latency_ms": self.average("nexus_agent_registry_latency_ms"),
                "avg_cost_usd": self.average("nexus_agent_registry_cost_usd"),
            }

    def record_registration(self) -> None:
        self.inc("nexus_agent_registry_registrations_total")

    def record_lookup(self) -> None:
        self.inc("nexus_agent_registry_lookups_total")

    def record_selection(self, *, candidates: int) -> None:
        self.inc("nexus_agent_registry_selections_total")
        self.observe("nexus_agent_registry_selection_candidates", float(candidates))

    def record_capability_hit(self, capability: str) -> None:
        self.inc(
            "nexus_agent_registry_capability_utilization_total",
            labels={"capability": capability},
        )

    def set_availability(self, value: float) -> None:
        self.set_gauge("nexus_agent_registry_availability", value)

    def set_health(self, value: float) -> None:
        self.set_gauge("nexus_agent_registry_health", value)

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._labeled.clear()
