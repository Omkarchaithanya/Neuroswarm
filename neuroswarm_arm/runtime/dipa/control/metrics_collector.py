"""MetricsCollector — control-plane counters/histograms."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any, Mapping


class MetricsCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._hist: dict[str, list[float]] = defaultdict(list)
        self._started = time.time()

    def incr(self, name: str, value: float = 1.0, **labels: Any) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] += value

    def gauge(self, name: str, value: float, **labels: Any) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def observe(self, name: str, value: float, **labels: Any) -> None:
        key = self._key(name, labels)
        with self._lock:
            bucket = self._hist[key]
            bucket.append(value)
            if len(bucket) > 2048:
                del bucket[:1024]

    def snapshot(self) -> Mapping[str, Any]:
        with self._lock:
            hist_summary = {
                k: {
                    "count": len(v),
                    "avg": (sum(v) / len(v)) if v else 0.0,
                    "p50": _percentile(v, 50),
                    "p95": _percentile(v, 95),
                }
                for k, v in self._hist.items()
            }
            return {
                "uptime_s": time.time() - self._started,
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": hist_summary,
            }

    @staticmethod
    def _key(name: str, labels: Mapping[str, Any]) -> str:
        if not labels:
            return name
        parts = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{parts}}}"


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]
