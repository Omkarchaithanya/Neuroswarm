"""MAKS telemetry — Prometheus + optional OpenTelemetry / Performix bridge."""

from __future__ import annotations

from typing import Any

from .metrics import MAKSMetrics


# Layer-10 signal names (stable ABI for Grafana / Performix)
TELEMETRY_SERIES: dict[str, str] = {
    "maks_memory_used": "gauge",
    "maks_shared_pages": "gauge",
    "maks_dedup_ratio": "gauge",
    "maks_compression_ratio": "gauge",
    "maks_provider_usage": "gauge",
    "maks_migration_rate": "gauge",
    "maks_lookup_latency": "gauge",
    "maks_reference_count": "gauge",
    "maks_hot_pages": "gauge",
    "maks_cold_pages": "gauge",
    "maks_warm_pages": "gauge",
    "maks_tier_distribution": "gauge",
    "maks_pressure": "gauge",
    "maks_fragmentation": "gauge",
    "maks_backend_statistics": "gauge",
    # legacy aliases kept for ABI
    "maks_memory_usage_bytes": "gauge",
    "maks_provider_usage_bytes": "gauge",
    "maks_cache_hit": "counter",
    "maks_cache_miss": "counter",
    "maks_migration_count": "counter",
    "maks_eviction_count": "counter",
}


class MAKSTelemetry:
    """Compose MAKSMetrics with Memory-OS gauges; optional OTel spans."""

    def __init__(self, metrics: MAKSMetrics | None = None, *, otel: object | None = None) -> None:
        self.metrics = metrics or MAKSMetrics()
        self.otel = otel
        self._migrations = 0
        self._lookups = 0
        # Register extended series on bridge
        for name, mtype in TELEMETRY_SERIES.items():
            if name not in self.metrics.types:
                self.metrics.types[name] = mtype
                self.metrics.help_text[name] = name.replace("_", " ")
                if self.metrics.bridge is not None and hasattr(self.metrics.bridge, "describe"):
                    try:
                        self.metrics.bridge.describe(name, mtype, name)
                    except Exception:
                        pass

    def inc(self, name: str, value: float = 1.0) -> None:
        self.metrics.inc(name, value)

    def set(self, name: str, value: float) -> None:
        self.metrics.set(name, value)

    def get(self, name: str) -> float:
        return self.metrics.get(name)

    def observe_latency(self, name: str, ms: float) -> None:
        self.metrics.observe_latency(name, ms)
        if name == "maks_lookup_latency_ms":
            self.set("maks_lookup_latency", self.get(name))

    def record_migration(self) -> None:
        self._migrations += 1
        self.inc("maks_migration_count")
        self.set("maks_migration_rate", float(self._migrations))

    def publish_pool(self, pool_stats: dict[str, Any], *, pressure: float = 0.0, fragmentation: float = 0.0) -> None:
        self.set("maks_memory_used", float(pool_stats.get("used_bytes", 0)))
        self.set("maks_memory_usage_bytes", float(pool_stats.get("used_bytes", 0)))
        self.set("maks_shared_pages", float(pool_stats.get("shared_pages", 0)))
        self.set("maks_hot_pages", float(pool_stats.get("hot_pages", 0)))
        self.set("maks_warm_pages", float(pool_stats.get("warm_pages", 0)))
        self.set("maks_cold_pages", float(pool_stats.get("cold_pages", 0)))
        self.set("maks_pressure", float(pressure))
        self.set("maks_fragmentation", float(fragmentation))
        # tier_distribution as packed hot*1e6 + warm*1e3 + cold (simple gauge)
        hot = int(pool_stats.get("hot_pages", 0))
        warm = int(pool_stats.get("warm_pages", 0))
        cold = int(pool_stats.get("cold_pages", 0))
        self.set("maks_tier_distribution", float(hot * 1_000_000 + warm * 1_000 + cold))

    def publish_ratios(
        self,
        *,
        dedup_ratio: float = 0.0,
        compression_ratio: float = 1.0,
        refcount: float = 0.0,
        provider_usage: float = 0.0,
    ) -> None:
        self.set("maks_dedup_ratio", float(dedup_ratio))
        self.set("maks_compression_ratio", float(compression_ratio))
        self.set("maks_reference_count", float(refcount))
        self.set("maks_provider_usage", float(provider_usage))
        self.set("maks_provider_usage_bytes", float(provider_usage))

    def span(self, name: str, attributes: dict[str, Any] | None = None) -> Any:
        """Optional OpenTelemetry span context manager; no-op if otel absent."""
        if self.otel is None:
            return _NullSpan()
        try:
            tracer = getattr(self.otel, "get_tracer", None)
            if tracer is None:
                return _NullSpan()
            t = tracer("maks")
            return t.start_as_current_span(name, attributes=attributes or {})
        except Exception:
            return _NullSpan()

    def snapshot(self) -> dict[str, float]:
        return self.metrics.snapshot()


class _NullSpan:
    def __enter__(self) -> _NullSpan:
        return self

    def __exit__(self, *args: object) -> None:
        return None
