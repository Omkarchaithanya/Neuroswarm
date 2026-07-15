"""Recovery execution metadata — order, depth, resume refs (no workflow run)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ._utils import new_id, utc_now
from .models import RollbackLevel, RollbackStrategyKind, _Frozen


class RecoveryExecutionMetadata(_Frozen):
    """Represents prepared recovery order / dependencies for a rollback plan.

    Does not execute workflows. Does not schedule. Materializes descriptors only.
    """

    recovery_id: str = Field(default_factory=lambda: new_id("rcv_"))
    rollback_id: str
    workflow_id: str
    execution_id: str
    rollback_plan_id: str | None = None
    recovery_order: list[str] = Field(default_factory=list)
    recovery_dependencies: dict[str, list[str]] = Field(default_factory=dict)
    resume_node: str | None = None
    resume_workflow: str | None = None
    resume_subgraph: str | None = None
    rollback_depth: int = 0
    rollback_duration_ms: float | None = None
    strategy: RollbackStrategyKind | None = None
    level: RollbackLevel | None = None
    checkpoint_reference: str | None = None
    prepared_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RollbackPlan(_Frozen):
    """Deterministic rollback plan produced by RollbackPlanner."""

    plan_id: str = Field(default_factory=lambda: new_id("rbplan_"))
    rollback_id: str = Field(default_factory=lambda: new_id("rb_"))
    workflow_id: str
    execution_id: str
    strategy: RollbackStrategyKind = RollbackStrategyKind.RESUME_CHECKPOINT
    level: RollbackLevel = RollbackLevel.WORKFLOW
    checkpoint_reference: str | None = None
    recovery_plan_reference: str | None = None
    target_node: str | None = None
    target_subgraph: str | None = None
    target_context: str | None = None
    target_budget: str | None = None
    target_nodes: list[str] = Field(default_factory=list)
    reason: str = ""
    recovery_order: list[str] = Field(default_factory=list)
    recovery_dependencies: dict[str, list[str]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)
