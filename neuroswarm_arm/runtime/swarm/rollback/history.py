"""Rollback history store — reasons, strategies, success, duration (no exec logs)."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from pydantic import Field

from ._utils import utc_now
from .execution import RollbackResult
from .models import RollbackAnalytics, RollbackStatus, RollbackStrategyKind, _Frozen
from .recovery import RollbackPlan
from .rollback import RollbackOperation


class HistoryEntry(_Frozen):
    """Single rollback history record."""

    rollback_id: str
    plan_id: str | None = None
    workflow_id: str
    execution_id: str
    strategy: RollbackStrategyKind
    reason: str = ""
    success: bool = True
    duration_ms: float = 0.0
    status: RollbackStatus = RollbackStatus.COMPLETED
    recorded_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RollbackHistoryView(_Frozen):
    """Ordered rollback history for an execution / workflow."""

    execution_id: str = ""
    workflow_id: str = ""
    entries: list[HistoryEntry] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def depth(self) -> int:
        return len(self.entries)


class RollbackHistoryStore:
    """In-memory history of rollback operations (no execution logs)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_execution: dict[str, list[HistoryEntry]] = {}
        self._by_workflow: dict[str, list[HistoryEntry]] = {}
        self._by_id: dict[str, HistoryEntry] = {}

    def record(
        self,
        *,
        operation: RollbackOperation | None = None,
        plan: RollbackPlan | None = None,
        result: RollbackResult | None = None,
        success: bool | None = None,
        duration_ms: float | None = None,
        reason: str | None = None,
    ) -> HistoryEntry:
        if operation is not None:
            rollback_id = operation.rollback_id
            workflow_id = operation.workflow_id
            execution_id = operation.execution_id
            strategy = operation.rollback_strategy
            reason_v = reason if reason is not None else operation.rollback_reason
            status = operation.status
            plan_id = None
        elif plan is not None:
            rollback_id = plan.rollback_id
            workflow_id = plan.workflow_id
            execution_id = plan.execution_id
            strategy = plan.strategy
            reason_v = reason if reason is not None else plan.reason
            status = (
                RollbackStatus.COMPLETED
                if success is not False
                else RollbackStatus.FAILED
            )
            plan_id = plan.plan_id
        elif result is not None:
            rollback_id = result.rollback_id
            workflow_id = result.workflow_id
            execution_id = result.execution_id
            strategy = (
                result.recovery.strategy
                if result.recovery and result.recovery.strategy
                else RollbackStrategyKind.RESUME_CHECKPOINT
            )
            reason_v = reason or ""
            status = result.status
            plan_id = result.plan_id
            if duration_ms is None:
                duration_ms = result.duration_ms
            if success is None:
                success = result.status == RollbackStatus.COMPLETED
        else:
            raise ValueError("operation, plan, or result required")

        entry = HistoryEntry(
            rollback_id=rollback_id,
            plan_id=plan_id,
            workflow_id=workflow_id,
            execution_id=execution_id,
            strategy=strategy,
            reason=reason_v,
            success=True if success is None else bool(success),
            duration_ms=float(duration_ms or 0.0),
            status=status,
        )
        with self._lock:
            self._by_id[rollback_id] = entry
            self._by_execution.setdefault(execution_id, []).append(entry)
            self._by_workflow.setdefault(workflow_id, []).append(entry)
        return entry

    def for_execution(self, execution_id: str) -> RollbackHistoryView:
        with self._lock:
            entries = list(self._by_execution.get(execution_id, []))
        workflow_id = entries[0].workflow_id if entries else ""
        return RollbackHistoryView(
            execution_id=execution_id,
            workflow_id=workflow_id,
            entries=entries,
        )

    def for_workflow(self, workflow_id: str) -> RollbackHistoryView:
        with self._lock:
            entries = list(self._by_workflow.get(workflow_id, []))
        execution_id = entries[0].execution_id if entries else ""
        return RollbackHistoryView(
            execution_id=execution_id,
            workflow_id=workflow_id,
            entries=entries,
        )

    def get(self, rollback_id: str) -> HistoryEntry | None:
        with self._lock:
            return self._by_id.get(rollback_id)

    def analytics(
        self,
        *,
        execution_id: str | None = None,
        workflow_id: str | None = None,
    ) -> RollbackAnalytics:
        with self._lock:
            if execution_id:
                entries = list(self._by_execution.get(execution_id, []))
            elif workflow_id:
                entries = list(self._by_workflow.get(workflow_id, []))
            else:
                entries = list(self._by_id.values())

        strategy_usage: dict[str, int] = {}
        success = failure = cancelled = 0
        duration_sum = 0.0
        for e in entries:
            strategy_usage[e.strategy.value] = (
                strategy_usage.get(e.strategy.value, 0) + 1
            )
            duration_sum += e.duration_ms
            if e.status == RollbackStatus.CANCELLED:
                cancelled += 1
            elif e.success:
                success += 1
            else:
                failure += 1
        n = len(entries)
        return RollbackAnalytics(
            execution_id=execution_id,
            workflow_id=workflow_id,
            total_rollbacks=n,
            success_count=success,
            failure_count=failure,
            cancelled_count=cancelled,
            strategy_usage=strategy_usage,
            mean_duration_ms=(duration_sum / n) if n else 0.0,
        )
