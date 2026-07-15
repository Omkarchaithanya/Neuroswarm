"""Named, independently scalable worker pools."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Callable

from ..interfaces.types import PoolKind
from ..topology.affinity_manager import AffinityManager
from .priority_scheduler import PriorityScheduler
from .queue_manager import QueuedTask, QueueManager


@dataclass
class WorkerStats:
    tasks_run: int = 0
    busy_s: float = 0.0
    idle_s: float = 0.0
    last_start: float = 0.0


@dataclass
class Worker:
    worker_id: str
    pool: PoolKind
    thread: threading.Thread | None = None
    stop: threading.Event = field(default_factory=threading.Event)
    stats: WorkerStats = field(default_factory=WorkerStats)
    locality_tag: str = ""


class WorkerPool:
    """One pool kind: N worker threads that poll the PriorityScheduler."""

    def __init__(
        self,
        kind: PoolKind,
        size: int,
        scheduler: PriorityScheduler,
        queues: QueueManager,
        *,
        on_task: Callable[[QueuedTask], None] | None = None,
        affinity: AffinityManager | None = None,
        name_prefix: str = "haoe",
    ) -> None:
        self.kind = kind
        self._size = max(1, size)
        self._scheduler = scheduler
        self._queues = queues
        self._on_task = on_task
        self._affinity = affinity
        self._name_prefix = name_prefix
        self._workers: list[Worker] = []
        self._started = False

    @property
    def size(self) -> int:
        return len(self._workers)

    def start(self) -> None:
        if self._started:
            return
        for _ in range(self._size):
            wid = self._queues.register_worker(self.kind)
            worker = Worker(worker_id=wid, pool=self.kind)
            worker.thread = threading.Thread(
                target=self._loop,
                args=(worker,),
                name=f"{self._name_prefix}-{self.kind.value}-{wid[-8:]}",
                daemon=True,
            )
            self._workers.append(worker)
            worker.thread.start()
        self._started = True

    def stop(self, timeout: float = 2.0) -> None:
        for w in self._workers:
            w.stop.set()
        for w in self._workers:
            if w.thread is not None:
                w.thread.join(timeout=timeout)
            self._queues.unregister_worker(self.kind, w.worker_id)
        self._workers.clear()
        self._started = False

    def utilization(self) -> float:
        if not self._workers:
            return 0.0
        busy = sum(1 for w in self._workers if w.stats.last_start > 0 and not w.stop.is_set())
        # Approximate: fraction of workers that have run at least one task recently.
        active = sum(1 for w in self._workers if w.stats.tasks_run > 0)
        return active / max(1, len(self._workers)) if busy else active / max(1, len(self._workers))

    def _loop(self, worker: Worker) -> None:
        while not worker.stop.is_set():
            task = self._scheduler.poll(worker.worker_id, self.kind)
            if task is None:
                worker.stop.wait(0.005)
                continue
            start = monotonic()
            worker.stats.last_start = start
            try:
                if self._affinity is not None and task.affinity.pin:
                    cores = self._affinity.resolve(
                        priority=task.priority, hint=task.affinity, pool=self.kind
                    )
                    self._affinity.apply(cores, pin=True)
                if self._on_task is not None:
                    self._on_task(task)
            finally:
                worker.stats.tasks_run += 1
                worker.stats.busy_s += monotonic() - start
                worker.stats.last_start = 0.0


class WorkerPoolManager:
    """Owns all eight pool kinds."""

    def __init__(
        self,
        scheduler: PriorityScheduler,
        queues: QueueManager,
        sizes: dict[PoolKind, int],
        *,
        on_task: Callable[[QueuedTask], None] | None = None,
        affinity: AffinityManager | None = None,
    ) -> None:
        self.pools: dict[PoolKind, WorkerPool] = {}
        for kind, size in sizes.items():
            self.pools[kind] = WorkerPool(
                kind, size, scheduler, queues, on_task=on_task, affinity=affinity
            )

    def start_all(self) -> None:
        for pool in self.pools.values():
            pool.start()

    def stop_all(self, timeout: float = 2.0) -> None:
        for pool in self.pools.values():
            pool.stop(timeout=timeout)

    def utilization(self) -> dict[str, float]:
        return {k.value: p.utilization() for k, p in self.pools.items()}
