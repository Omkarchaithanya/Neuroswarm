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

    def mark(self, phase: ExecutionPhase) -> None:
        self.phase = phase
