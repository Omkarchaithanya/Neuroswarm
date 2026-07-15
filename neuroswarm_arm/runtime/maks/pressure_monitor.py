"""Pressure monitor — single telemetry source for RTG / Cascade / HAOE."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class PressureSnapshot:
    pressure: float
    used_bytes: int
    ram_budget_bytes: int
    entries: float = 0.0
    pages: int = 0
    shared_pages: int = 0
    hot_pages: int = 0
    warm_pages: int = 0
    cold_pages: int = 0
    dedup_ratio: float = 0.0
    compression_ratio: float = 0.0
    fragmentation: float = 0.0
    threshold: float = 0.70

    def as_dict(self) -> dict[str, Any]:
        return {
            "pressure": self.pressure,
            "used_bytes": self.used_bytes,
            "ram_budget_bytes": self.ram_budget_bytes,
            "entries": self.entries,
            "pages": self.pages,
            "shared_pages": self.shared_pages,
            "hot_pages": self.hot_pages,
            "warm_pages": self.warm_pages,
            "cold_pages": self.cold_pages,
            "dedup_ratio": self.dedup_ratio,
            "compression_ratio": self.compression_ratio,
            "fragmentation": self.fragmentation,
            "threshold": self.threshold,
            "over_threshold": self.pressure >= self.threshold,
        }


class PressureMonitor:
    """Compose allocator + pool stats into one pressure signal."""

    def __init__(
        self,
        *,
        ram_budget_bytes: int,
        threshold: float = 0.70,
        used_bytes_fn: Callable[[], int] | None = None,
        pool_stats_fn: Callable[[], dict[str, Any]] | None = None,
        dedup_ratio_fn: Callable[[], float] | None = None,
        compression_ratio_fn: Callable[[], float] | None = None,
    ) -> None:
        self.ram_budget_bytes = max(1, int(ram_budget_bytes))
        self.threshold = float(threshold)
        self._used_bytes_fn = used_bytes_fn or (lambda: 0)
        self._pool_stats_fn = pool_stats_fn or (lambda: {})
        self._dedup_ratio_fn = dedup_ratio_fn or (lambda: 0.0)
        self._compression_ratio_fn = compression_ratio_fn or (lambda: 1.0)

    def pressure(self) -> float:
        return min(1.0, self._used_bytes_fn() / float(self.ram_budget_bytes))

    def snapshot(self) -> PressureSnapshot:
        pool = self._pool_stats_fn() or {}
        used = int(self._used_bytes_fn())
        pages = int(pool.get("pages", 0))
        handles = int(pool.get("handles", 0))
        # crude fragmentation: unused page slots vs handles
        frag = 0.0
        if pages > 0 and handles > 0:
            frag = max(0.0, min(1.0, 1.0 - (handles / float(pages))))
        return PressureSnapshot(
            pressure=min(1.0, used / float(self.ram_budget_bytes)),
            used_bytes=used,
            ram_budget_bytes=self.ram_budget_bytes,
            entries=float(handles),
            pages=pages,
            shared_pages=int(pool.get("shared_pages", 0)),
            hot_pages=int(pool.get("hot_pages", 0)),
            warm_pages=int(pool.get("warm_pages", 0)),
            cold_pages=int(pool.get("cold_pages", 0)),
            dedup_ratio=float(self._dedup_ratio_fn()),
            compression_ratio=float(self._compression_ratio_fn()),
            fragmentation=frag,
            threshold=self.threshold,
        )

    def over_threshold(self) -> bool:
        return self.pressure() >= self.threshold

    # Callable surface for HAOE / RTG injection
    def __call__(self) -> dict[str, Any]:
        return self.snapshot().as_dict()
