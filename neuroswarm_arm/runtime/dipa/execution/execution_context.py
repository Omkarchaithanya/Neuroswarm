"""Per-request execution context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..interfaces.types import (
    CorrelationIds,
    ExecutionPhase,
    ExecutionPlan,
    InferenceRequest,
)


@dataclass
class ExecutionContext:
    request: InferenceRequest
    plan: ExecutionPlan | None = None
    phase: ExecutionPhase = ExecutionPhase.ADMITTED
    ids: CorrelationIds = field(default_factory=CorrelationIds)
    baggage: dict[str, Any] = field(default_factory=dict)
    kv_handle: str | None = None
    id_slot: int | None = None
    quant: str = ""
    backend_name: str = ""
    model_name: str = ""
    warm: bool = False
    cancelled: bool = False
    errors: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    affinity_draft: list[int] = field(default_factory=list)
    affinity_verify: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.plan is None or not getattr(self.plan, "speculation", False):
            return
        meta = dict(getattr(self.plan, "metadata", None) or {})
        topo = meta.get("topology") or {}
        if not isinstance(topo, dict):
            return
        draft = topo.get("affinity_draft") or topo.get("draft_cores") or []
        verify = topo.get("affinity_verify") or topo.get("verify_cores") or []
        cores = topo.get("affinity_cores") or []
        if draft:
            self.affinity_draft = [int(c) for c in draft]
        elif cores:
            self.affinity_draft = [int(c) for c in cores]
        if verify:
            self.affinity_verify = [int(c) for c in verify]
        elif cores and not self.affinity_verify:
            # Remaining cores after draft partition when only affinity_cores set.
            draft_set = set(self.affinity_draft)
            self.affinity_verify = [int(c) for c in cores if int(c) not in draft_set] or [
                int(c) for c in cores
            ]

    def mark(self, phase: ExecutionPhase) -> None:
        self.phase = phase
