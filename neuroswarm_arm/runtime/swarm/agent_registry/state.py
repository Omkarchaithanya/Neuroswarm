"""Mutable runtime state mirror for a registered agent."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._utils import utc_now
from .lifecycle import LifecycleState


class AgentRuntimeState(BaseModel):
    """Runtime-only mutable state (separate from Agent definition)."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    agent_id: str
    lifecycle: LifecycleState = LifecycleState.CREATED
    in_flight: int = 0
    total_executions: int = 0
    frozen: bool = False
    enabled: bool = True
    last_selected_at: datetime | None = None
    last_error: str | None = None
    bindings: dict[str, str] = Field(default_factory=dict)
    baggage: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utc_now)

    def touch(self) -> AgentRuntimeState:
        return self.model_copy(update={"updated_at": utc_now()})

    def mark_busy(self) -> AgentRuntimeState:
        return self.model_copy(
            update={
                "lifecycle": LifecycleState.BUSY,
                "in_flight": self.in_flight + 1,
                "updated_at": utc_now(),
            }
        )

    def mark_ready(self) -> AgentRuntimeState:
        inflight = max(0, self.in_flight - 1)
        life = LifecycleState.BUSY if inflight > 0 else LifecycleState.READY
        return self.model_copy(
            update={
                "lifecycle": life,
                "in_flight": inflight,
                "updated_at": utc_now(),
            }
        )

    def mark_selected(self) -> AgentRuntimeState:
        return self.model_copy(
            update={
                "last_selected_at": utc_now(),
                "total_executions": self.total_executions + 1,
                "updated_at": utc_now(),
            }
        )
