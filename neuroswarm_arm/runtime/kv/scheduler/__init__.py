"""Background hot/warm/cold migration scheduler."""

from __future__ import annotations

import asyncio
import heapq
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from ..interfaces.migrator import IKVMigrator
from ..interfaces.types import BlockTemperature, StorageTier
from ..migration import KVTieringEngine
from ..utils.logging import get_logger

logger = get_logger("neuroswarm.kv.scheduler")


@dataclass(order=True)
class MigrationJob:
    priority: int
    enqueued_at: float
    physical_id: str = field(compare=False)
    target_tier: StorageTier = field(compare=False)
    temperature: BlockTemperature = field(compare=False, default=BlockTemperature.COLD)


class MigrationScheduler(IKVMigrator):
    """Non-blocking priority queues with optional background thread."""

    def __init__(
        self,
        tiering: KVTieringEngine,
        *,
        interval_s: float = 1.0,
        enable_background: bool = True,
    ) -> None:
        self.tiering = tiering
        self.interval_s = interval_s
        self._hot: list[MigrationJob] = []
        self._warm: list[MigrationJob] = []
        self._cold: list[MigrationJob] = []
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._completed = 0
        if enable_background:
            self.start()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="kv-migration", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def enqueue(
        self,
        physical_id: str,
        target_tier: StorageTier,
        *,
        priority: int = 0,
        temperature: BlockTemperature = BlockTemperature.COLD,
    ) -> None:
        job = MigrationJob(
            priority=-int(priority),  # heapq is min-heap; negate for higher-first
            enqueued_at=time.time(),
            physical_id=physical_id,
            target_tier=target_tier,
            temperature=temperature,
        )
        with self._lock:
            if temperature == BlockTemperature.HOT:
                heapq.heappush(self._hot, job)
            elif temperature == BlockTemperature.WARM:
                heapq.heappush(self._warm, job)
            else:
                heapq.heappush(self._cold, job)

    def should_migrate(self) -> bool:
        return self.tiering.should_migrate()

    def _pop_next(self) -> MigrationJob | None:
        with self._lock:
            for queue in (self._hot, self._warm, self._cold):
                if queue:
                    return heapq.heappop(queue)
        return None

    async def run_once(self) -> int:
        completed = 0
        # Pressure-driven demotions first
        if self.should_migrate():
            completed += await self.tiering.demote_under_pressure()
        # Explicit jobs
        while True:
            job = self._pop_next()
            if job is None:
                break
            try:
                ok = await self.tiering.migrate_block(job.physical_id, job.target_tier)
                if ok:
                    completed += 1
            except Exception as exc:
                logger.warning("job_failed id=%s err=%s", job.physical_id, exc)
        self._completed += completed
        return completed

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                asyncio.run(self.run_once())
            except Exception as exc:
                logger.warning("scheduler_loop_error err=%s", exc)
            self._stop.wait(self.interval_s)

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._hot) + len(self._warm) + len(self._cold)

    @property
    def completed(self) -> int:
        return self._completed
