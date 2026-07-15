"""Core scheduler facade — wraps PriorityScheduler + ResourceAllocator."""

from __future__ import annotations

from typing import Any

from ..interfaces import IScheduler
from ..interfaces.types import AffinityHint, PoolKind, PriorityClass, ResourceEstimate
from ..scheduling.priority_scheduler import PriorityScheduler
from ..scheduling.resource_allocator import ResourceAllocator


class HAOECoreScheduler(IScheduler):
    """Kernel-facing scheduler API used by dispatcher / workflow scheduler."""

    def __init__(
        self,
        priority: PriorityScheduler,
        allocator: ResourceAllocator,
    ) -> None:
        self.priority = priority
        self.allocator = allocator

    def submit(
        self,
        task_id: str,
        *,
        priority: PriorityClass = PriorityClass.NORMAL,
        pool: PoolKind = PoolKind.BACKGROUND,
        estimate: ResourceEstimate | None = None,
        affinity: AffinityHint | None = None,
        payload: Any = None,
    ) -> None:
        alloc = self.allocator.allocate(
            pool=pool,
            priority=priority,
            numa_node=affinity.numa_node if affinity else None,
            locality_tag=affinity.locality_tag if affinity else "",
            pin=affinity.pin if affinity else False,
        )
        self.priority.submit(
            task_id,
            priority=alloc.priority,
            pool=alloc.pool,
            estimate=estimate or alloc.estimate,
            affinity=affinity or alloc.affinity,
            payload=payload,
        )

    def poll(self, worker_id: str, pool: PoolKind) -> Any | None:
        return self.priority.poll(worker_id, pool)

    def steal(self, thief_id: str, pool: PoolKind) -> Any | None:
        return self.priority.steal(thief_id, pool)

    def depth(self, pool: PoolKind | None = None) -> int:
        return self.priority.depth(pool)
