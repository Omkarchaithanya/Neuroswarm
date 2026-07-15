"""MAKS scheduler — share / migrate / cleanup / warm / prefetch / evict."""

from __future__ import annotations

import asyncio
import threading
import time
from typing import TYPE_CHECKING

from .models import KVState, LocalityHint
from .metadata import now_ts

if TYPE_CHECKING:
    from .manager import KVManager


class MAKSScheduler:
    def __init__(
        self,
        manager: KVManager | None = None,
        *,
        interval_s: float = 1.0,
        enable_background: bool = True,
        pressure_threshold: float = 0.70,
    ) -> None:
        self._manager = manager
        self.interval_s = interval_s
        self.enable_background = enable_background
        self.pressure_threshold = pressure_threshold
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pending_prefetch: list = []
        self._locality: dict[str, LocalityHint] = {}

    def bind(self, manager: KVManager) -> None:
        self._manager = manager

    def set_locality(self, agent_id: str, hint: LocalityHint) -> None:
        self._locality[agent_id] = hint

    def get_locality(self, agent_id: str) -> LocalityHint | None:
        return self._locality.get(agent_id)

    def enqueue_prefetch(self, req) -> None:  # noqa: ANN001
        self._pending_prefetch.append(req)

    def start(self) -> None:
        if not self.enable_background or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="maks-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            try:
                asyncio.run(self.tick())
            except Exception:
                continue

    async def tick(self) -> None:
        if self._manager is None:
            return
        mgr = self._manager
        # Drain prefetch queue
        while self._pending_prefetch:
            req = self._pending_prefetch.pop(0)
            try:
                await mgr.prefetch(req)
            except Exception:
                pass
        # TTL / orphan cleanup
        await mgr.cleanup()
        # Pressure-driven demotion / eviction
        pressure = mgr.pressure()
        if pressure >= self.pressure_threshold:
            await mgr.relieve_pressure()
