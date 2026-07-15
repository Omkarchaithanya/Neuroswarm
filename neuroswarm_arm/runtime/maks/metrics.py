"""Prometheus / bridge metrics for MAKS."""

from __future__ import annotations

from threading import RLock
from typing import Any


class MAKSMetrics:
    """In-process counters/gauges; optional bridge with describe/inc/set."""

    def __init__(self, bridge: object | None = None) -> None:
        self.bridge = bridge
        self._lock = RLock()
        self.values: dict[str, float] = {}
        self.types: dict[str, str] = {
            "maks_cache_hit": "counter",
            "maks_cache_miss": "counter",
            "maks_dedup_ratio": "gauge",
            "maks_reuse_ratio": "gauge",
            "maks_migration_count": "counter",
            "maks_eviction_count": "counter",
            "maks_provider_usage_bytes": "gauge",
            "maks_memory_usage_bytes": "gauge",
            "maks_refcount_total": "gauge",
            "maks_hot_entries": "gauge",
            "maks_warm_entries": "gauge",
            "maks_cold_entries": "gauge",
            "maks_compression_ratio": "gauge",
            "maks_backend_latency_ms": "gauge",
            "maks_allocation_latency_ms": "gauge",
            "maks_share_latency_ms": "gauge",
            "maks_entries": "gauge",
        }
        self.help_text = {k: k.replace("_", " ") for k in self.types}
        if bridge is not None and hasattr(bridge, "describe"):
            for name, mtype in self.types.items():
                try:
                    bridge.describe(name, mtype, self.help_text.get(name, ""))
                except Exception:
                    pass

    def inc(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self.values[name] = self.values.get(name, 0.0) + value
        if self.bridge is not None and hasattr(self.bridge, "inc"):
            try:
                self.bridge.inc(name, value)
            except Exception:
                pass

    def set(self, name: str, value: float) -> None:
        with self._lock:
            self.values[name] = float(value)
        if self.bridge is not None and hasattr(self.bridge, "set"):
            try:
                self.bridge.set(name, value)
            except Exception:
                pass

    def get(self, name: str) -> float:
        with self._lock:
            return float(self.values.get(name, 0.0))

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return dict(self.values)

    def observe_latency(self, name: str, ms: float) -> None:
        # EMA-style
        prev = self.get(name)
        if prev <= 0:
            self.set(name, ms)
        else:
            self.set(name, 0.8 * prev + 0.2 * ms)
