"""Async buffered metric updates — keep hot path off registry locks when possible."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from typing import TYPE_CHECKING

from .schemas import MetricUpdate, MetricUpdateOp

if TYPE_CHECKING:
    from .registry import MetricRegistry


class AsyncMetricBuffer:
    """Thread-safe ring of MetricUpdate drained by a background flusher."""

    def __init__(
        self,
        registry: MetricRegistry,
        *,
        max_size: int = 65536,
        flush_ms: int = 25,
        flush_batch: int = 2048,
    ) -> None:
        self.registry = registry
        self.max_size = max(1, int(max_size))
        self.flush_ms = max(1, int(flush_ms))
        self.flush_batch = max(1, int(flush_batch))
        self._q: deque[MetricUpdate] = deque()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._task: asyncio.Task[None] | None = None
        self.drops = 0

    def push(self, update: MetricUpdate) -> bool:
        with self._lock:
            if len(self._q) >= self.max_size:
                self.drops += 1
                self.registry.record_drop()
                return False
            self._q.append(update)
            return True

    def inc(self, name: str, value: float = 1.0, *, labels: dict[str, str] | None = None) -> bool:
        return self.push(
            MetricUpdate(name=name, op=MetricUpdateOp.INC, value=value, labels=labels or {})
        )

    def set(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> bool:
        return self.push(
            MetricUpdate(name=name, op=MetricUpdateOp.SET, value=value, labels=labels or {})
        )

    def observe(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> bool:
        return self.push(
            MetricUpdate(name=name, op=MetricUpdateOp.OBSERVE, value=value, labels=labels or {})
        )

    def _drain_once(self) -> int:
        batch: list[MetricUpdate] = []
        with self._lock:
            while self._q and len(batch) < self.flush_batch:
                batch.append(self._q.popleft())
        for item in batch:
            if item.op == MetricUpdateOp.INC:
                self.registry.inc(item.name, item.value, labels=item.labels)
            elif item.op == MetricUpdateOp.SET:
                self.registry.set(item.name, item.value, labels=item.labels)
            elif item.op == MetricUpdateOp.OBSERVE:
                self.registry.observe(
                    item.name, item.value, labels=item.labels, exemplar=item.exemplar
                )
            elif item.op == MetricUpdateOp.INFO:
                self.registry.info(item.name, item.labels)
        return len(batch)

    def flush(self) -> int:
        total = 0
        while True:
            n = self._drain_once()
            total += n
            if n == 0:
                break
        return total

    def _run_sync(self) -> None:
        while not self._stop.is_set():
            self._drain_once()
            time.sleep(self.flush_ms / 1000.0)
        self.flush()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_sync, name="rmf-metric-buffer", daemon=True)
        self._thread.start()

    def stop(self, *, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        self.flush()

    async def start_asyncio(self) -> None:
        if self._task is not None and not self._task.done():
            return

        async def _loop() -> None:
            try:
                while True:
                    self._drain_once()
                    await asyncio.sleep(self.flush_ms / 1000.0)
            except asyncio.CancelledError:
                self.flush()
                raise

        self._task = asyncio.create_task(_loop(), name="rmf-metric-buffer")

    async def stop_asyncio(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self.flush()
