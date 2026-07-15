"""Affinity manager — policy layer above ThreadPinning / AffinityProvider."""

from __future__ import annotations

from typing import Sequence

from ..interfaces.types import AffinityHint, PoolKind, PriorityClass
from .numa_adapter import NumaAdapter
from .thread_pinning import ThreadPinning
from .topology_service import TopologyService


class AffinityManager:
    """Select cores for a task and optionally pin the worker thread."""

    def __init__(
        self,
        topology: TopologyService,
        pinning: ThreadPinning,
        numa: NumaAdapter | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        self._topo = topology
        self._pinning = pinning
        self._numa = numa or NumaAdapter(topology)
        self._enabled = enabled

    def resolve(
        self,
        *,
        priority: PriorityClass = PriorityClass.NORMAL,
        hint: AffinityHint | None = None,
        pool: PoolKind = PoolKind.BACKGROUND,
    ) -> list[int]:
        if hint and hint.preferred_cores:
            return list(hint.preferred_cores)

        placement = self._numa.place(hint.numa_node if hint else None)
        if priority in (PriorityClass.CRITICAL, PriorityClass.HIGH):
            preferred = [c for c in self._topo.fast_cores() if c in set(placement.cores)]
            return preferred or placement.cores or self._topo.fast_cores()

        # Background / normal → efficiency cores when available
        if pool in (PoolKind.BACKGROUND, PoolKind.MAINTENANCE, PoolKind.TELEMETRY):
            preferred = [
                c for c in self._topo.efficiency_cores() if c in set(placement.cores)
            ]
            return preferred or placement.cores or self._topo.efficiency_cores()

        return placement.cores or self._topo.core_ids()

    def apply(self, cores: Sequence[int], *, pin: bool = False) -> bool:
        if not self._enabled or not pin:
            return False
        return self._pinning.pin(cores)

    @property
    def efficiency(self) -> float:
        return self._pinning.efficiency
