"""RuntimeProfiler — rolling inference metrics for AQR decisions."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class RuntimeProfiler:
    window: int = 128
    _lock: Lock = field(default_factory=Lock)
    _series: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=128)))
    _last: dict[str, float] = field(default_factory=dict)
    quant_util: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    backend_util: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    model_util: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def __post_init__(self) -> None:
        self._series = defaultdict(lambda: deque(maxlen=self.window))

    def record_outcome(
        self,
        *,
        model: str,
        quant: str,
        backend: str,
        tokens_per_sec: float = 0.0,
        ttft_ms: float = 0.0,
        decode_latency_ms: float = 0.0,
        prefill_latency_ms: float = 0.0,
        cache_hit_rate: float = 0.0,
        kv_pressure: float = 0.0,
        queue_length: float = 0.0,
        worker_util: float = 0.0,
    ) -> None:
        with self._lock:
            self._push("tokens_per_sec", tokens_per_sec)
            self._push("ttft_ms", ttft_ms)
            self._push("decode_latency_ms", decode_latency_ms)
            self._push("prefill_latency_ms", prefill_latency_ms)
            self._push("cache_hit_rate", cache_hit_rate)
            self._push("kv_pressure", kv_pressure)
            self._push("queue_length", queue_length)
            self._push("worker_util", worker_util)
            self.quant_util[quant] += 1
            self.backend_util[backend] += 1
            self.model_util[model] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "averages": {k: self._avg(v) for k, v in self._series.items()},
                "last": dict(self._last),
                "quant_utilization": dict(self.quant_util),
                "backend_utilization": dict(self.backend_util),
                "model_utilization": dict(self.model_util),
            }

    def avg(self, key: str, default: float = 0.0) -> float:
        with self._lock:
            series = self._series.get(key)
            if not series:
                return default
            return self._avg(series)

    def _push(self, key: str, value: float) -> None:
        self._series[key].append(float(value))
        self._last[key] = float(value)

    @staticmethod
    def _avg(series: deque[float]) -> float:
        if not series:
            return 0.0
        return sum(series) / len(series)
