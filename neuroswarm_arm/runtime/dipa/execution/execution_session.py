"""Execution session — tracks one inference admission."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any
from uuid import uuid4

from ..interfaces.types import ExecutionPhase, InferenceResponse
from .execution_context import ExecutionContext


@dataclass
class ExecutionSession:
    ctx: ExecutionContext
    session_id: str = field(default_factory=lambda: uuid4().hex)
    started_at: float = field(default_factory=monotonic)
    finished_at: float | None = None
    response: InferenceResponse | None = None
    cancelled: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def elapsed_ms(self) -> float:
        end = self.finished_at if self.finished_at is not None else monotonic()
        return (end - self.started_at) * 1000.0

    def finish(self, response: InferenceResponse) -> InferenceResponse:
        self.response = response
        self.finished_at = monotonic()
        self.ctx.mark(ExecutionPhase.COMPLETED)
        return response

    def cancel(self) -> None:
        self.cancelled = True
        self.ctx.cancelled = True
        self.ctx.mark(ExecutionPhase.CANCELLED)
        self.finished_at = monotonic()
