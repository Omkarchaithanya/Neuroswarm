"""Per-worker and global overflow queues with locality tags."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic
from typing import Any
from uuid import uuid4

from ..interfaces.types import (
    AffinityHint,
    PoolKind,
    PriorityClass,
    ResourceEstimate,
)


@dataclass(slots=True)
class QueuedTask:
    """Unit of work sitting in a worker or overflow queue."""

    task_id: str
    priority: PriorityClass = PriorityClass.NORMAL
    pool: PoolKind = PoolKind.BACKGROUND
    estimate: ResourceEstimate = field(default_factory=ResourceEstimate)
    affinity: AffinityHint = field(default_factory=AffinityHint)
    payload: Any = None
    enqueued_at: float = field(default_factory=monotonic)
    deadline_monotonic: float | None = None
    effective_priority: float = 0.0  # lower is more urgent after aging
    locality_tag: str = ""

    def __post_init__(self) -> None:
        self.effective_priority = float(int(self.priority))
        if self.affinity and self.affinity.locality_tag:
            self.locality_tag = self.affinity.locality_tag


class WorkerQueue:
    """Owner pushes/pops left; thieves steal from the right (oldest eligible)."""

    def __init__(self, worker_id: str) -> None:
        self.worker_id = worker_id
        self._dq: deque[QueuedTask] = deque()
        self._lock = Lock()

    def push(self, task: QueuedTask) -> None:
        with self._lock:
            self._dq.appendleft(task)

    def pop(self) -> QueuedTask | None:
        with self._lock:
            if not self._dq:
                return None
            return self._dq.popleft()

    def steal_oldest(self) -> QueuedTask | None:
        with self._lock:
            if not self._dq:
                return None
            return self._dq.pop()

    def __len__(self) -> int:
        with self._lock:
            return len(self._dq)


class OverflowQueue:
    """Global overflow when all private queues are saturated / unbound tasks."""

    def __init__(self) -> None:
        self._items: list[QueuedTask] = []
        self._lock = Lock()

    def push(self, task: QueuedTask) -> None:
        with self._lock:
            self._items.append(task)
            self._items.sort(key=lambda t: (t.effective_priority, t.enqueued_at))

    def pop(self) -> QueuedTask | None:
        with self._lock:
            if not self._items:
                return None
            return self._items.pop(0)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


class QueueManager:
    """Owns per-pool worker queues + overflow."""

    def __init__(self) -> None:
        self._pools: dict[PoolKind, dict[str, WorkerQueue]] = {
            p: {} for p in PoolKind
        }
        self._overflow: dict[PoolKind, OverflowQueue] = {
            p: OverflowQueue() for p in PoolKind
        }
        self._lock = Lock()

    def register_worker(self, pool: PoolKind, worker_id: str | None = None) -> str:
        wid = worker_id or f"{pool.value}-{uuid4().hex[:8]}"
        with self._lock:
            self._pools[pool][wid] = WorkerQueue(wid)
        return wid

    def unregister_worker(self, pool: PoolKind, worker_id: str) -> None:
        with self._lock:
            self._pools[pool].pop(worker_id, None)

    def worker_ids(self, pool: PoolKind) -> list[str]:
        with self._lock:
            return list(self._pools[pool].keys())

    def push_private(self, pool: PoolKind, worker_id: str, task: QueuedTask) -> None:
        q = self._pools[pool].get(worker_id)
        if q is None:
            self.push_overflow(pool, task)
            return
        q.push(task)

    def push_overflow(self, pool: PoolKind, task: QueuedTask) -> None:
        self._overflow[pool].push(task)

    def pop_private(self, pool: PoolKind, worker_id: str) -> QueuedTask | None:
        q = self._pools[pool].get(worker_id)
        if q is None:
            return None
        return q.pop()

    def pop_overflow(self, pool: PoolKind) -> QueuedTask | None:
        return self._overflow[pool].pop()

    def steal(self, pool: PoolKind, thief_id: str) -> QueuedTask | None:
        victims = [wid for wid in self.worker_ids(pool) if wid != thief_id]
        # Prefer longest victim queue (simple load signal).
        victims.sort(key=lambda wid: len(self._pools[pool].get(wid, WorkerQueue(wid))), reverse=True)
        for vid in victims:
            q = self._pools[pool].get(vid)
            if q is None:
                continue
            stolen = q.steal_oldest()
            if stolen is not None:
                return stolen
        return None

    def depth(self, pool: PoolKind | None = None) -> int:
        pools = [pool] if pool is not None else list(PoolKind)
        total = 0
        for p in pools:
            total += len(self._overflow[p])
            for q in self._pools[p].values():
                total += len(q)
        return total

    def pick_least_loaded(self, pool: PoolKind) -> str | None:
        ids = self.worker_ids(pool)
        if not ids:
            return None
        return min(ids, key=lambda wid: len(self._pools[pool][wid]))
