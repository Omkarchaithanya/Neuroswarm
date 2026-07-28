"""ARM / Axion hardware adapters — dual-mode locality (NUMA vs cache-aware)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(slots=True)
class ArmPlacement:
    draft_numa_node: int = 0
    verify_numa_node: int = 0
    numa_available: bool = False
    locality: float = 1.0
    kleidiai: bool = False
    message: str = "Axion single-UMA cache-aware affinity"
    locality_mode: str = "cache_aware"
    draft_cores: list[int] = field(default_factory=list)
    verify_cores: list[int] = field(default_factory=list)


class ArmRuntimeAdapter:
    """Best-effort topology placement: NUMA when multi-node, else core partitions."""

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = dict((config or {}).get("arm") or config or {})
        self._placement = ArmPlacement()

    def detect(self, hardware: Any | None = None) -> ArmPlacement:
        from neuroswarm_arm.runtime.haoe.topology.locality_scheduler import (
            resolve_locality_plan,
        )
        from neuroswarm_arm.runtime.haoe.topology.cpu_topology import read_online_cpus

        numa_nodes = 1
        kleidiai = False
        online = read_online_cpus()
        if hardware is not None:
            numa_nodes = int(getattr(hardware, "numa_nodes", 1) or 1)
            feats = getattr(hardware, "features", None) or {}
            if isinstance(feats, dict):
                kleidiai = bool(feats.get("kleidiai") or feats.get("i8mm"))
            hw_cores = getattr(hardware, "cores", None) or getattr(hardware, "logical_cpus", None)
            if hw_cores:
                online = [int(c) for c in hw_cores]

        multi = numa_nodes > 1 and bool(self.config.get("numa_aware", True))
        plan = resolve_locality_plan(
            numa_nodes=numa_nodes, online_cores=online, multi_node=multi
        )
        draft = plan.cores_for("draft")
        verify = plan.cores_for("verify")

        if multi and plan.mode == "numa_aware":
            self._placement = ArmPlacement(
                draft_numa_node=0,
                verify_numa_node=1,
                numa_available=True,
                locality=1.0,
                kleidiai=kleidiai,
                message="multi-NUMA placement (numactl)",
                locality_mode="numa_aware",
                draft_cores=draft,
                verify_cores=verify,
            )
        else:
            self._placement = ArmPlacement(
                draft_numa_node=0,
                verify_numa_node=0,
                numa_available=False,
                locality=1.0,
                kleidiai=kleidiai,
                message=plan.reason or "single-UMA cache-aware CPU affinity",
                locality_mode=plan.mode,
                draft_cores=draft or (online[:2] if online else [0]),
                verify_cores=verify or (online[2:] if len(online) > 2 else online),
            )
        return self._placement

    @property
    def placement(self) -> ArmPlacement:
        return self._placement

    def pin_current_thread(self, pool: str = "draft") -> bool:
        """Best-effort pin to draft or verify core partition."""
        if pool == "draft" and not self.config.get("pin_draft_pool", True):
            return False
        if pool == "verify" and not self.config.get("pin_verify_pool", True):
            return False
        try:
            import os

            if not hasattr(os, "sched_setaffinity"):
                return False
            if not self._placement.draft_cores and not self._placement.verify_cores:
                self.detect()
            cores = (
                self._placement.draft_cores
                if pool == "draft"
                else self._placement.verify_cores
            )
            if not cores:
                cores = [0]
            os.sched_setaffinity(0, set(int(c) for c in cores))
            return True
        except (OSError, AttributeError, PermissionError):
            return False


class PerformixHook:
    """Observation sink for ARM Performix / EvolutionLoop (no ownership)."""

    def __init__(self) -> None:
        self.last: dict[str, float] = {}

    def record(self, fields: Mapping[str, float]) -> None:
        self.last = {str(k): float(v) for k, v in fields.items()}
