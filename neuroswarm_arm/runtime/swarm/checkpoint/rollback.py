"""Rollback metadata — no durable undo / execution logic."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from pydantic import Field

from ._utils import new_id, utc_now
from .checkpoint import Checkpoint
from .events import EventBus, RollbackPlanned
from .exceptions import RollbackPlanningError
from .metrics import CheckpointMetrics
from .models import FailureContext, _Frozen


class RollbackRecord(_Frozen):
    """Single rollback notification entry."""

    rollback_id: str = Field(default_factory=lambda: new_id("rb_"))
    execution_id: str
    workflow_id: str
    target_checkpoint: str | None = None
    target_nodes: list[str] = Field(default_factory=list)
    reason: str = ""
    depth: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RollbackHistory(_Frozen):
    """Ordered rollback history for an execution."""

    execution_id: str
    workflow_id: str
    records: list[RollbackRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def depth(self) -> int:
        return len(self.records)


class RollbackMetadataBuilder:
    """Build rollback metadata / history (notification only)."""

    def __init__(
        self,
        *,
        events: EventBus | None = None,
        metrics: CheckpointMetrics | None = None,
    ) -> None:
        self.events = events or EventBus()
        self.metrics = metrics or CheckpointMetrics()
        self._histories: dict[str, list[RollbackRecord]] = {}

    def plan(
        self,
        failure: FailureContext,
        *,
        checkpoint: Checkpoint | None = None,
        target_nodes: Sequence[str] | None = None,
        depth: int | None = None,
    ) -> RollbackRecord:
        targets = (
            list(target_nodes)
            if target_nodes is not None
            else list(failure.failed_nodes)
        )
        target_ckpt = checkpoint.checkpoint_id if checkpoint else None
        if not targets and not target_ckpt:
            raise RollbackPlanningError("no rollback targets and no checkpoint")

        existing = self._histories.get(failure.execution_id, [])
        record = RollbackRecord(
            execution_id=failure.execution_id,
            workflow_id=failure.workflow_id,
            target_checkpoint=target_ckpt,
            target_nodes=targets,
            reason=failure.reason,
            depth=depth if depth is not None else len(existing),
        )
        existing = [*existing, record]
        self._histories[failure.execution_id] = existing
        self.metrics.incr("rollback_count")
        self.events.emit(
            RollbackPlanned(
                workflow_id=failure.workflow_id,
                execution_id=failure.execution_id,
                rollback_id=record.rollback_id,
                target_checkpoint=target_ckpt or "",
                depth=record.depth,
            )
        )
        return record

    def history(self, execution_id: str, workflow_id: str = "") -> RollbackHistory:
        records = list(self._histories.get(execution_id, []))
        return RollbackHistory(
            execution_id=execution_id,
            workflow_id=workflow_id or (records[0].workflow_id if records else ""),
            records=records,
        )
