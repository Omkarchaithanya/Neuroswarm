"""ARM / Axion hardware adapters (isolated from strategy logic)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(slots=True)
class ArmPlacement:
    draft_numa_node: int = 0
    verify_numa_node: int = 0
    numa_available: bool = False
    locality: float = 1.0
    kleidiai: bool = False
    message: str = "Axion single-NUMA fallback"


class ArmRuntimeAdapter:
    """Best-effort NUMA / affinity / KleidiAI / Performix hooks."""

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = dict((config or {}).get("arm") or config or {})
        self._placement = ArmPlacement()

    def detect(self, hardware: Any | None = None) -> ArmPlacement:
        numa_nodes = 1
        kleidiai = False
        if hardware is not None:
            numa_nodes = int(getattr(hardware, "numa_nodes", 1) or 1)
            feats = getattr(hardware, "features", None) or {}
            if isinstance(feats, dict):
                kleidiai = bool(feats.get("kleidiai") or feats.get("i8mm"))
        multi = numa_nodes > 1 and bool(self.config.get("numa_aware", True))
        if multi:
            self._placement = ArmPlacement(
                draft_numa_node=0,
                verify_numa_node=1,
                numa_available=True,
                locality=1.0,
                kleidiai=kleidiai,
                message="multi-NUMA placement",
            )
        else:
            self._placement = ArmPlacement(
                draft_numa_node=0,
                verify_numa_node=0,
                numa_available=False,
                locality=1.0,
                kleidiai=kleidiai,
                message="UNAVAILABLE" if self.config.get("report_unavailable", True) else "single-node",
            )
        return self._placement

    @property
    def placement(self) -> ArmPlacement:
        return self._placement

    def pin_current_thread(self, pool: str = "draft") -> bool:
        """Best-effort; returns False when affinity unavailable."""
        if pool == "draft" and not self.config.get("pin_draft_pool", True):
            return False
        if pool == "verify" and not self.config.get("pin_verify_pool", True):
            return False
        try:
            import os

            if not hasattr(os, "sched_setaffinity"):
                return False
            # Soft pin to first CPU; production can inject topology cores.
            os.sched_setaffinity(0, {0})
            return True
        except (OSError, AttributeError, PermissionError):
            return False


class PerformixHook:
    """Observation sink for ARM Performix / EvolutionLoop (no ownership)."""

    def __init__(self) -> None:
        self.last: dict[str, float] = {}

    def record(self, fields: Mapping[str, float]) -> None:
        self.last = {str(k): float(v) for k, v in fields.items()}
