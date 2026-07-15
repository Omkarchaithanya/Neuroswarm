"""Dynamic batch sizing."""

from __future__ import annotations


class DynamicBatcher:
    def __init__(self, target_latency_ms: float = 50.0, max_batch: int = 32) -> None:
        self.target_latency_ms = target_latency_ms
        self.max_batch = max_batch
        self._ema_latency = target_latency_ms

    def observe(self, latency_ms: float) -> None:
        self._ema_latency = 0.8 * self._ema_latency + 0.2 * latency_ms

    def recommend_size(self, queued: int) -> int:
        if self._ema_latency <= 0:
            return min(queued, self.max_batch)
        scale = self.target_latency_ms / max(self._ema_latency, 1.0)
        size = max(1, int(self.max_batch * min(1.0, scale)))
        return min(queued, size, self.max_batch)
