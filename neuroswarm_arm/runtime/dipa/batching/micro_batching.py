"""Micro-batching coalescer."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import monotonic
from typing import Any


@dataclass
class MicroBatch:
    items: list[Any] = field(default_factory=list)
    opened_at: float = field(default_factory=monotonic)


class MicroBatcher:
    def __init__(self, max_batch: int = 8, window_ms: float = 10.0) -> None:
        self.max_batch = max_batch
        self.window_ms = window_ms
        self._lock = Lock()
        self._current = MicroBatch()

    def offer(self, item: Any) -> list[Any] | None:
        """Add item; return flushed batch when full or window elapsed."""
        with self._lock:
            self._current.items.append(item)
            age_ms = (monotonic() - self._current.opened_at) * 1000.0
            if (
                len(self._current.items) >= self.max_batch
                or age_ms >= self.window_ms
            ):
                batch = list(self._current.items)
                self._current = MicroBatch()
                return batch
            return None

    def flush(self) -> list[Any]:
        with self._lock:
            batch = list(self._current.items)
            self._current = MicroBatch()
            return batch
