"""Resource allocator — maps estimates to worker/affinity/budget decisions."""

from __future__ import annotations

from dataclasses import dataclass

from ..interfaces.types import (
    AffinityHint,
    PoolKind,
    PriorityClass,
    ResourceEstimate,
)
from ..topology.affinity_manager import AffinityManager
from .load_balancer import LoadBalancer
from .task_cost_estimator import TaskCostEstimator


@dataclass(slots=True)
class Allocation:
    pool: PoolKind
    priority: PriorityClass
    affinity: AffinityHint
    estimate: ResourceEstimate
    cpu_budget: float
    memory_budget_bytes: int


class ResourceAllocator:
    def __init__(
        self,
        estimator: TaskCostEstimator,
        balancer: LoadBalancer,
        affinity: AffinityManager | None = None,
    ) -> None:
        self._estimator = estimator
        self._balancer = balancer
        self._affinity = affinity

    def allocate(
        self,
        *,
        pool: PoolKind,
        priority: PriorityClass = PriorityClass.NORMAL,
        numa_node: int | None = None,
        locality_tag: str = "",
        pin: bool = False,
        task_weight: float = 1.0,
        agent_weight: float = 1.0,
        expected_latency_ms: float = 50.0,
    ) -> Allocation:
        chosen_pool = self._balancer.recommend_pool(pool)
        estimate = self._estimator.estimate(
            pool=chosen_pool,
            priority=priority,
            task_weight=task_weight,
            agent_weight=agent_weight,
            expected_latency_ms=expected_latency_ms,
            queue_length=self._balancer.queue_depths().get(chosen_pool.value, 0),
        )
        hint = AffinityHint(numa_node=numa_node, locality_tag=locality_tag, pin=pin)
        if self._affinity is not None:
            hint.preferred_cores = self._affinity.resolve(
                priority=priority, hint=hint, pool=chosen_pool
            )
        return Allocation(
            pool=chosen_pool,
            priority=priority,
            affinity=hint,
            estimate=estimate,
            cpu_budget=estimate.cpu_cost,
            memory_budget_bytes=estimate.memory_bytes,
        )
