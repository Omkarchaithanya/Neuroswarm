from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any


@dataclass
class CacheManager:
    """L1 process cache; L2/L3 hooks optional."""

    l1: dict[str, Any] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0
    _lock: RLock = field(default_factory=RLock)

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key in self.l1:
                self.hits += 1
                return self.l1[key]
            self.misses += 1
            return None

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self.l1[key] = value

    def clear(self) -> None:
        with self._lock:
            self.l1.clear()

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total) if total else 0.0
