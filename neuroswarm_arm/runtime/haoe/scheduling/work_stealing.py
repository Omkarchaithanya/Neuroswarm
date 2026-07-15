"""Work-stealing strategy over QueueManager."""

from __future__ import annotations

from ..interfaces.types import PoolKind
from .queue_manager import QueuedTask, QueueManager


class WorkStealingScheduler:
    """Idle workers steal oldest eligible task; prefer locality_tag match."""

    def __init__(self, queues: QueueManager, *, attempts: int = 3) -> None:
        self._queues = queues
        self._attempts = max(1, attempts)
        self.steal_count = 0
        self.locality_hits = 0

    def take(self, worker_id: str, pool: PoolKind, *, locality_tag: str = "") -> QueuedTask | None:
        # 1. Private queue
        task = self._queues.pop_private(pool, worker_id)
        if task is not None:
            return task
        # 2. Overflow
        task = self._queues.pop_overflow(pool)
        if task is not None:
            return task
        # 3. Steal
        for _ in range(self._attempts):
            stolen = self._queues.steal(pool, worker_id)
            if stolen is None:
                break
            self.steal_count += 1
            if locality_tag and stolen.locality_tag == locality_tag:
                self.locality_hits += 1
                return stolen
            # Accept non-local if no better option this round.
            return stolen
        return None
