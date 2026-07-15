"""Windowed aggregators for feedback loop / in-process recording mirrors."""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Mapping

from .schemas import AggregatedWindow

if TYPE_CHECKING:
    from .registry import MetricRegistry


class WindowAggregator:
    """Keep rolling windows of observed values for avg / p95 / p99."""

    def __init__(
        self,
        registry: MetricRegistry | None = None,
        *,
        window_s: float = 60.0,
        max_samples: int = 4096,
    ) -> None:
        self.registry = registry
        self.window_s = max(1.0, float(window_s))
        self.max_samples = max(16, int(max_samples))
        self._lock = threading.Lock()
        self._samples: dict[str, deque[tuple[float, float]]] = defaultdict(deque)

    def observe(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        key = name
        if labels:
            parts = [f"{k}={v}" for k, v in sorted(labels.items())]
            key = f"{name}|{','.join(parts)}"
        now = time.time()
        with self._lock:
            q = self._samples[key]
            q.append((now, float(value)))
            while q and (now - q[0][0]) > self.window_s:
                q.popleft()
            while len(q) > self.max_samples:
                q.popleft()

    def _percentile(self, values: list[float], p: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        idx = min(len(ordered) - 1, max(0, int(math.ceil(p * len(ordered)) - 1)))
        return ordered[idx]

    def window(self, name: str, *, labels: Mapping[str, str] | None = None) -> AggregatedWindow:
        key = name
        label_map = dict(labels or {})
        if labels:
            parts = [f"{k}={v}" for k, v in sorted(labels.items())]
            key = f"{name}|{','.join(parts)}"
        with self._lock:
            q = list(self._samples.get(key, ()))
        values = [v for _, v in q]
        total = float(sum(values))
        count = float(len(values))
        avg = total / count if count else 0.0
        return AggregatedWindow(
            name=name,
            avg=avg,
            p95=self._percentile(values, 0.95),
            p99=self._percentile(values, 0.99),
            count=count,
            sum=total,
            labels=label_map,
        )

    def snapshot(self) -> dict[str, AggregatedWindow]:
        with self._lock:
            keys = list(self._samples.keys())
        out: dict[str, AggregatedWindow] = {}
        for key in keys:
            if "|" in key:
                name, _ = key.split("|", 1)
            else:
                name = key
            out[key] = self.window(name) if "|" not in key else self._window_key(key, name)
        return out

    def _window_key(self, key: str, name: str) -> AggregatedWindow:
        with self._lock:
            q = list(self._samples.get(key, ()))
        values = [v for _, v in q]
        total = float(sum(values))
        count = float(len(values))
        labels: dict[str, str] = {}
        if "|" in key:
            for part in key.split("|", 1)[1].split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    labels[k] = v
        return AggregatedWindow(
            name=name,
            avg=(total / count if count else 0.0),
            p95=self._percentile(values, 0.95),
            p99=self._percentile(values, 0.99),
            count=count,
            sum=total,
            labels=labels,
        )

    def publish_recording_mirrors(self) -> None:
        """Write in-process recording-rule style gauges into registry."""
        if self.registry is None:
            return
        for key, win in self.snapshot().items():
            base = win.name
            self.registry.set(f"nexus_rmf_avg_{base}", win.avg, labels=win.labels)
            self.registry.set(f"nexus_rmf_p95_{base}", win.p95, labels=win.labels)
            self.registry.set(f"nexus_rmf_p99_{base}", win.p99, labels=win.labels)
