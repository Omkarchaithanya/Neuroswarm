"""Runtime-local metric counters before bridging to Prometheus."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock


@dataclass
class RuntimeMetrics:
    """In-process metric buffer; HAOETelemetry flushes to MetricsStore."""

    lock: Lock = field(default_factory=Lock)
    counters: dict[str, float] = field(default_factory=dict)
    gauges: dict[str, float] = field(default_factory=dict)
    histograms: dict[str, list[float]] = field(default_factory=dict)

    def inc(self, name: str, value: float = 1.0) -> None:
        with self.lock:
            self.counters[name] = self.counters.get(name, 0.0) + value

    def set(self, name: str, value: float) -> None:
        with self.lock:
            self.gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        with self.lock:
            self.histograms.setdefault(name, []).append(value)
            # Keep a rolling window to bound memory.
            buf = self.histograms[name]
            if len(buf) > 1024:
                self.histograms[name] = buf[-512:]

    def snapshot(self) -> dict[str, float]:
        with self.lock:
            out = dict(self.counters)
            out.update(self.gauges)
            for name, values in self.histograms.items():
                if values:
                    out[f"{name}_count"] = float(len(values))
                    out[f"{name}_sum"] = float(sum(values))
                    out[f"{name}_last"] = float(values[-1])
            return out
