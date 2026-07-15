"""Pace token emission with a fixed inter-chunk delay."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class ChunkScheduler:
    """Sleep between chunks to smooth client delivery."""

    delay_ms: float = 5.0
    _last_emit: float = field(default=0.0, init=False, repr=False)

    @property
    def delay_s(self) -> float:
        return max(0.0, self.delay_ms) / 1000.0

    async def wait(self) -> None:
        """Await the configured delay since the previous emit (if any)."""
        delay = self.delay_s
        if delay <= 0:
            self._last_emit = time.monotonic()
            return
        now = time.monotonic()
        if self._last_emit > 0:
            elapsed = now - self._last_emit
            remaining = delay - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
        self._last_emit = time.monotonic()

    def wait_sync(self) -> None:
        delay = self.delay_s
        if delay <= 0:
            self._last_emit = time.monotonic()
            return
        now = time.monotonic()
        if self._last_emit > 0:
            remaining = delay - (now - self._last_emit)
            if remaining > 0:
                time.sleep(remaining)
        self._last_emit = time.monotonic()

    def reset(self) -> None:
        self._last_emit = 0.0
