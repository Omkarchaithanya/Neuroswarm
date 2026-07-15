"""Priority scheduler with aging, deadlines, and latency-budget scoring."""

from __future__ import annotations

from time import monotonic
from typing import Any

from ..interfaces import IScheduler
from ..interfaces.types import (
    AffinityHint,
    PoolKind,
    PriorityClass,
    ResourceEstimate,
)
from .queue_manager import QueuedTask, QueueManager
from .work_stealing import WorkStealingScheduler


class PriorityScheduler(IScheduler):
    """Admission control: score task → place onto least-loaded worker or overflow."""

    def __init__(
        self,
        queues: QueueManager,
        stealer: WorkStealingScheduler,
        *,
        aging_enabled: bool = True,
        aging_step: float = 0.1,
    ) -> None:
        self._queues = queues
        self._stealer = stealer
        self._aging_enabled = aging_enabled
        self._aging_step = aging_step
        self.submitted = 0

    def submit(
        self,
        task_id: str,
        *,
        priority: PriorityClass = PriorityClass.NORMAL,
        pool: PoolKind = PoolKind.BACKGROUND,
        estimate: ResourceEstimate | None = None,
        affinity: AffinityHint | None = None,
        payload: Any = None,
        deadline_s: float | None = None,
        latency_budget_ms: float | None = None,
    ) -> None:
        est = estimate or ResourceEstimate()
        if latency_budget_ms is not None:
            est.expected_latency_ms = latency_budget_ms
        hint = affinity or AffinityHint()
        task = QueuedTask(
            task_id=task_id,
            priority=priority,
            pool=pool,
            estimate=est,
            affinity=hint,
            payload=payload,
            deadline_monotonic=(
                monotonic() + deadline_s if deadline_s is not None else None
            ),
            locality_tag=hint.locality_tag,
        )
        task.effective_priority = self._score(task)
        victim = self._queues.pick_least_loaded(pool)
        if victim is None:
            self._queues.push_overflow(pool, task)
        else:
            self._queues.push_private(pool, victim, task)
        self.submitted += 1

    def poll(self, worker_id: str, pool: PoolKind) -> QueuedTask | None:
        self.age_pool(pool)
        return self._stealer.take(worker_id, pool)

    def steal(self, thief_id: str, pool: PoolKind) -> QueuedTask | None:
        return self._queues.steal(pool, thief_id)

    def depth(self, pool: PoolKind | None = None) -> int:
        return self._queues.depth(pool)

    def age_pool(self, pool: PoolKind) -> None:
        """Dynamic priority aging — waiting tasks become more urgent over time."""
        if not self._aging_enabled:
            return
        now = monotonic()
        # Aging is applied lazily when tasks are observed in overflow.
        # Private queues age on steal/pop via effective_priority adjustment in _score path.
        # Soft-touch overflow: re-score in place.
        overflow = self._queues._overflow[pool]
        with overflow._lock:
            for task in overflow._items:
                waited = now - task.enqueued_at
                task.effective_priority = max(
                    0.0,
                    float(int(task.priority)) - waited * self._aging_step,
                )
                if task.deadline_monotonic is not None and now >= task.deadline_monotonic:
                    task.effective_priority = float(int(PriorityClass.CRITICAL)) - 1.0
            overflow._items.sort(key=lambda t: (t.effective_priority, t.enqueued_at))

    def _score(self, task: QueuedTask) -> float:
        base = float(int(task.priority))
        cost = task.estimate.score() * 0.01
        # Higher cost slightly elevates urgency for CRITICAL/HIGH only.
        if task.priority <= PriorityClass.HIGH:
            base -= min(0.5, cost)
        if task.deadline_monotonic is not None:
            remaining = task.deadline_monotonic - monotonic()
            if remaining < 1.0:
                base -= 1.0
        return base
