"""Prometheus-style metrics for Adaptive Context Runtime."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any


class ACRMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counters: dict[str, float] = defaultdict(float)
        self.gauges: dict[str, float] = {}
        self.latencies_ms: dict[str, list[float]] = defaultdict(list)

    def inc(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self.counters[name] += value

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self.gauges[name] = value

    def observe_ms(self, name: str, ms: float) -> None:
        with self._lock:
            bucket = self.latencies_ms[name]
            bucket.append(ms)
            if len(bucket) > 500:
                del bucket[:250]

    def timed(self, name: str):
        metrics = self

        class _Timer:
            def __enter__(self_inner):
                self_inner._t0 = time.perf_counter()
                return self_inner

            def __exit__(self_inner, *args):
                ms = (time.perf_counter() - self_inner._t0) * 1000.0
                metrics.observe_ms(name, ms)
                metrics.inc(f"{name}_total")

        return _Timer()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latency_avg = {
                k: (sum(v) / len(v) if v else 0.0) for k, v in self.latencies_ms.items()
            }
            return {
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "latency_avg_ms": latency_avg,
            }

    def prometheus_text(self) -> str:
        snap = self.snapshot()
        lines: list[str] = []
        for k, v in snap["counters"].items():
            lines.append(f"neuroswarm_acr_{k} {v}")
        for k, v in snap["gauges"].items():
            lines.append(f"neuroswarm_acr_{k} {v}")
        for k, v in snap["latency_avg_ms"].items():
            lines.append(f"neuroswarm_acr_{k}_avg_ms {v}")
        return "\n".join(lines) + ("\n" if lines else "")
