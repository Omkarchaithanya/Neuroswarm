"""Rollback apply — materialize state descriptors only (no workflow run)."""

from __future__ import annotations

import time
from typing import Any

from pydantic import Field

from ._utils import new_id, utc_now
from .events import (
    EventBus,
    RecoveryFinished,
    RecoveryPrepared,
    RollbackCompleted,
    RollbackFailed,
    RollbackStarted,
)
from .exceptions import RollbackExecutionError
from .interfaces import (
    IArmoraBudgetRollbackPort,
    ICheckpointRollbackPort,
    IPerformixRollbackPort,
    ISwarmContextRollbackPort,
)
from .lifecycle import transition
from .metadata import RollbackExecutionMetadata
from .metrics import RollbackMetrics
from .models import RollbackStatus, _Frozen
from .recovery import RecoveryExecutionMetadata, RollbackPlan
from .snapshots import (
    BudgetSnapshotRef,
    ContextSnapshotRef,
    RollbackSnapshotBundle,
)


class RollbackResult(_Frozen):
    """Result of applying a rollback plan — restored state descriptors only."""

    result_id: str = Field(default_factory=lambda: new_id("rbr_"))
    rollback_id: str
    plan_id: str
    workflow_id: str
    execution_id: str
    status: RollbackStatus = RollbackStatus.COMPLETED
    duration_ms: float = 0.0
    restored: RollbackSnapshotBundle = Field(default_factory=RollbackSnapshotBundle)
    recovery: RecoveryExecutionMetadata | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RollbackExecutor:
    """Apply rollback plan → RollbackResult (repository/history side effects only)."""

    def __init__(
        self,
        *,
        events: EventBus | None = None,
        metrics: RollbackMetrics | None = None,
        checkpoint_port: ICheckpointRollbackPort | None = None,
        context_port: ISwarmContextRollbackPort | None = None,
        budget_port: IArmoraBudgetRollbackPort | None = None,
        performix_port: IPerformixRollbackPort | None = None,
    ) -> None:
        self.events = events or EventBus()
        self.metrics = metrics or RollbackMetrics()
        self.checkpoint_port = checkpoint_port
        self.context_port = context_port
        self.budget_port = budget_port
        self.performix_port = performix_port

    def prepare(self, plan: RollbackPlan) -> RecoveryExecutionMetadata:
        meta = RecoveryExecutionMetadata(
            rollback_id=plan.rollback_id,
            workflow_id=plan.workflow_id,
            execution_id=plan.execution_id,
            rollback_plan_id=plan.plan_id,
            recovery_order=list(plan.recovery_order),
            recovery_dependencies=dict(plan.recovery_dependencies),
            resume_node=plan.target_node,
            resume_workflow=plan.workflow_id,
            resume_subgraph=plan.target_subgraph,
            rollback_depth=len(plan.recovery_order),
            strategy=plan.strategy,
            level=plan.level,
            checkpoint_reference=plan.checkpoint_reference,
            metadata=dict(plan.metadata),
        )
        self.events.emit(
            RecoveryPrepared(
                plan.rollback_id,
                workflow_id=plan.workflow_id,
                execution_id=plan.execution_id,
                recovery_id=meta.recovery_id,
                depth=meta.rollback_depth,
            )
        )
        return meta

    def execute(
        self,
        plan: RollbackPlan,
        *,
        recovery: RecoveryExecutionMetadata | None = None,
    ) -> RollbackResult:
        started = time.perf_counter()
        self.events.emit(
            RollbackStarted(
                plan.rollback_id,
                workflow_id=plan.workflow_id,
                execution_id=plan.execution_id,
                plan_id=plan.plan_id,
                strategy=plan.strategy.value,
            )
        )
        try:
            recovery = recovery or self.prepare(plan)
            restored = self._materialize(plan)
            duration_ms = (time.perf_counter() - started) * 1000.0
            recovery_data = recovery.model_dump(mode="python")
            recovery_data["rollback_duration_ms"] = duration_ms
            recovery = RecoveryExecutionMetadata.model_validate(recovery_data)

            result = RollbackResult(
                rollback_id=plan.rollback_id,
                plan_id=plan.plan_id,
                workflow_id=plan.workflow_id,
                execution_id=plan.execution_id,
                status=RollbackStatus.COMPLETED,
                duration_ms=duration_ms,
                restored=restored,
                recovery=recovery,
            )
            self.metrics.incr("success_count")
            self.metrics.record_duration(duration_ms)
            self.metrics.record_recovery_latency(duration_ms)
            self.metrics.record_strategy(plan.strategy.value)
            if self.performix_port is not None:
                self.performix_port.record_rollback_sample(
                    plan.rollback_id,
                    duration_ms=duration_ms,
                    strategy=plan.strategy.value,
                )
            self.events.emit(
                RollbackCompleted(
                    plan.rollback_id,
                    workflow_id=plan.workflow_id,
                    execution_id=plan.execution_id,
                    duration_ms=duration_ms,
                )
            )
            self.events.emit(
                RecoveryFinished(
                    plan.rollback_id,
                    workflow_id=plan.workflow_id,
                    execution_id=plan.execution_id,
                    duration_ms=duration_ms,
                )
            )
            return result
        except Exception as exc:  # noqa: BLE001
            duration_ms = (time.perf_counter() - started) * 1000.0
            self.metrics.incr("failure_count")
            self.metrics.record_duration(duration_ms)
            self.events.emit(
                RollbackFailed(
                    plan.rollback_id,
                    workflow_id=plan.workflow_id,
                    execution_id=plan.execution_id,
                    error=str(exc),
                )
            )
            raise RollbackExecutionError(str(exc)) from exc

    def _materialize(self, plan: RollbackPlan) -> RollbackSnapshotBundle:
        context_ref: ContextSnapshotRef | None = None
        budget_ref: BudgetSnapshotRef | None = None
        meta: dict[str, Any] = {"strategy": plan.strategy.value}

        if plan.checkpoint_reference and self.checkpoint_port is not None:
            if not self.checkpoint_port.checkpoint_exists(plan.checkpoint_reference):
                raise RollbackExecutionError(
                    f"checkpoint missing: {plan.checkpoint_reference}"
                )
            ckpt = self.checkpoint_port.get_checkpoint(plan.checkpoint_reference)
            if isinstance(ckpt, dict):
                meta["checkpoint"] = ckpt
            elif hasattr(ckpt, "model_dump"):
                meta["checkpoint"] = ckpt.model_dump(mode="json")
            else:
                meta["checkpoint"] = {"checkpoint_id": plan.checkpoint_reference}

        if plan.target_context and self.context_port is not None:
            snap_id = self.context_port.latest_snapshot_id(plan.target_context)
            context_ref = ContextSnapshotRef(
                context_id=plan.target_context,
                context_snapshot_id=snap_id,
            )
        elif plan.target_context:
            context_ref = ContextSnapshotRef(context_id=plan.target_context)

        if plan.target_budget and self.budget_port is not None:
            budget_ref = BudgetSnapshotRef(
                envelope_id=self.budget_port.envelope_id() or plan.target_budget,
                remaining=dict(self.budget_port.remaining()),
                frozen=self.budget_port.is_frozen(),
            )
        elif plan.target_budget:
            budget_ref = BudgetSnapshotRef(envelope_id=plan.target_budget)

        return RollbackSnapshotBundle(
            context=context_ref,
            budget=budget_ref,
            metadata=meta,
        )


def stamp_metadata(
    meta: RollbackExecutionMetadata,
    status: RollbackStatus,
    *,
    duration_ms: float | None = None,
    error: str | None = None,
) -> RollbackExecutionMetadata:
    """Advance execution metadata timestamps for a status transition."""
    transition(meta.rollback_id, meta.status, status)
    data = meta.model_dump(mode="python")
    data["status"] = status
    now = utc_now()
    if status == RollbackStatus.VALIDATED:
        data["validated_at"] = now
    elif status == RollbackStatus.PREPARED:
        data["prepared_at"] = now
    elif status == RollbackStatus.COMPLETED:
        data["completed_at"] = now
    elif status == RollbackStatus.FAILED:
        data["failed_at"] = now
        data["error"] = error
    elif status == RollbackStatus.CANCELLED:
        data["cancelled_at"] = now
    if duration_ms is not None:
        data["duration_ms"] = duration_ms
    return RollbackExecutionMetadata.model_validate(data)
