"""Load balancer across pools and workers."""

from __future__ import annotations

from ..interfaces.types import PoolKind
from .queue_manager import QueueManager
from .worker_pool import WorkerPoolManager


class LoadBalancer:
    """Advise pool selection and detect saturation."""

    def __init__(self, queues: QueueManager, pools: WorkerPoolManager | None = None) -> None:
        self._queues = queues
        self._pools = pools

    def queue_depths(self) -> dict[str, int]:
        return {p.value: self._queues.depth(p) for p in PoolKind}

    def is_saturated(self, pool: PoolKind, threshold: int = 32) -> bool:
        return self._queues.depth(pool) >= threshold

    def recommend_pool(self, preferred: PoolKind) -> PoolKind:
        """Keep preferred unless heavily saturated — then spill to BACKGROUND."""
        if not self.is_saturated(preferred):
            return preferred
        if preferred is not PoolKind.BACKGROUND and not self.is_saturated(PoolKind.BACKGROUND):
            return PoolKind.BACKGROUND
        return preferred

    def snapshot(self) -> dict[str, object]:
        util = self._pools.utilization() if self._pools else {}
        return {"depths": self.queue_depths(), "utilization": util}
