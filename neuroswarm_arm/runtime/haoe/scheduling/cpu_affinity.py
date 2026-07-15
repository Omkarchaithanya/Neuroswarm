"""CPU affinity helpers used by the scheduling layer."""

from __future__ import annotations

from typing import Sequence

from ..topology.affinity_manager import AffinityManager


class CPUAffinity:
    """Thin scheduling-facing wrapper around AffinityManager."""

    def __init__(self, manager: AffinityManager) -> None:
        self._manager = manager

    def bind_current(self, cores: Sequence[int]) -> bool:
        return self._manager.apply(cores, pin=True)

    @property
    def efficiency(self) -> float:
        return self._manager.efficiency
