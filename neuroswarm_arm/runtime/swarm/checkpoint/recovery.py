"""Recovery plan models — planning only, no execution."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ._utils import new_id, utc_now
from .models import RecoveryStrategy, _Frozen


class RecoveryPlan(_Frozen):
    """Deterministic recovery plan produced by RecoveryPlanner."""

    plan_id: str = Field(default_factory=lambda: new_id("rplan_"))
    workflow_id: str
    execution_id: str
    strategy: RecoveryStrategy
    checkpoint_id: str | None = None
    resume_node_id: str | None = None
    resume_subgraph_id: str | None = None
    target_nodes: list[str] = Field(default_factory=list)
    reason: str = ""
    rollback_notify: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)
