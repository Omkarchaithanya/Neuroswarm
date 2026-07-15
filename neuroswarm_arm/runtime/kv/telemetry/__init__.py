"""KV Prometheus telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock

from ..interfaces.telemetry import IKVTelemetry

METRIC_DEFS: dict[str, tuple[str, str]] = {
    "kv_blocks_total": ("gauge", "Total physical KV blocks"),
    "kv_blocks_shared": ("gauge", "Physical KV blocks with refcount > 1"),
    "kv_reference_count": ("gauge", "Sum of reference counts across physical blocks"),
    "kv_prefix_hits": ("counter", "Prefix cache hits"),
    "kv_prefix_misses": ("counter", "Prefix cache misses"),
    "kv_restore_latency": ("gauge", "Last restore latency in milliseconds"),
    "kv_checkpoint_latency": ("gauge", "Last checkpoint latency in milliseconds"),
    "kv_ram_usage": ("gauge", "RAM tier usage in bytes"),
    "kv_storage_usage": ("gauge", "Total storage usage in bytes"),
    "kv_compression_ratio": ("gauge", "Average compression ratio"),
    "kv_migration_count": ("counter", "Completed block migrations"),
    "kv_evictions": ("counter", "Blocks demoted under memory pressure"),
    "kv_reuse_ratio": ("gauge", "Prefix reuse ratio"),
    "kv_dedup_ratio": ("gauge", "Content deduplication hit ratio"),
    "kv_fragmentation": ("gauge", "Fragmentation proxy 0..1"),
    "kv_hit_rate": ("gauge", "Prefix hit rate 0..1"),
    "kv_miss_rate": ("gauge", "Prefix miss rate 0..1"),
}


@dataclass
class KVTelemetry(IKVTelemetry):
    lock: RLock = field(default_factory=RLock)
    values: dict[str, float] = field(default_factory=dict)
    types: dict[str, str] = field(default_factory=dict)
    help_text: dict[str, str] = field(default_factory=dict)
    bridge: object | None = None  # optional MetricsStore

    def __post_init__(self) -> None:
        for name, (mtype, help_text) in METRIC_DEFS.items():
            self.describe(name, mtype, help_text)
            self.values.setdefault(name, 0.0)

    def describe(self, name: str, metric_type: str, help_text: str) -> None:
        with self.lock:
            self.types[name] = metric_type
            self.help_text[name] = help_text

    def inc(self, name: str, value: float = 1.0) -> None:
        with self.lock:
            self.values[name] = self.values.get(name, 0.0) + value
        self._bridge_inc(name, value)

    def set(self, name: str, value: float) -> None:
        with self.lock:
            self.values[name] = float(value)
        self._bridge_set(name, value)

    def observe(self, name: str, value: float) -> None:
        # Treat observations as latest gauge samples for simplicity.
        self.set(name, value)

    def snapshot(self) -> dict[str, float]:
        with self.lock:
            return dict(self.values)

    def export_prometheus(self) -> str:
        with self.lock:
            lines: list[str] = []
            for key in sorted(self.values):
                mtype = self.types.get(key, "gauge")
                help_text = self.help_text.get(key)
                if help_text:
                    lines.append(f"# HELP {key} {help_text}")
                lines.append(f"# TYPE {key} {mtype}")
                lines.append(f"{key} {self.values[key]}")
            return "\n".join(lines) + "\n"

    def _bridge_inc(self, name: str, value: float) -> None:
        if self.bridge is not None and hasattr(self.bridge, "inc"):
            self.bridge.inc(name, value)

    def _bridge_set(self, name: str, value: float) -> None:
        if self.bridge is not None and hasattr(self.bridge, "set"):
            self.bridge.set(name, value)
