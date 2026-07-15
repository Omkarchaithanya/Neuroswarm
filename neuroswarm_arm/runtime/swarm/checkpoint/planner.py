"""Deterministic recovery planning — no execution side effects."""

from __future__ import annotations

from typing import Sequence

from .checkpoint import Checkpoint
from .events import EventBus, RecoveryPlanned
from .exceptions import RecoveryPlanningError
from .metrics import CheckpointMetrics
from .models import FailureContext, RecoveryStrategy
from .recovery import RecoveryPlan


class RecoveryPlanner:
    """Plan resume / restart / rollback-notify from available checkpoints."""

    def __init__(
        self,
        *,
        events: EventBus | None = None,
        metrics: CheckpointMetrics | None = None,
    ) -> None:
        self.events = events or EventBus()
        self.metrics = metrics or CheckpointMetrics()

    def plan(
        self,
        failure: FailureContext,
        checkpoints: Sequence[Checkpoint],
        *,
        prefer_node: bool = False,
        prefer_subgraph: bool = False,
    ) -> RecoveryPlan:
        active = [
            c
            for c in checkpoints
            if c.workflow_id == failure.workflow_id
            and c.execution_id == failure.execution_id
        ]
        active_sorted = sorted(active, key=lambda c: c.timestamp, reverse=True)

        if not active_sorted:
            plan = RecoveryPlan(
                workflow_id=failure.workflow_id,
                execution_id=failure.execution_id,
                strategy=RecoveryStrategy.RESTART_WORKFLOW,
                reason=failure.reason or "no_checkpoint_available",
                target_nodes=list(failure.failed_nodes),
                metadata={"available_checkpoints": 0},
            )
            self._emit(plan)
            return plan

        latest = active_sorted[0]

        if prefer_subgraph and (failure.subgraph_id or latest.graph_snapshot):
            subgraph_id = failure.subgraph_id
            if subgraph_id is None and latest.graph_snapshot is not None:
                subgraph_id = latest.graph_snapshot.subgraph_id
            if subgraph_id:
                plan = RecoveryPlan(
                    workflow_id=failure.workflow_id,
                    execution_id=failure.execution_id,
                    strategy=RecoveryStrategy.RESUME_SUBGRAPH,
                    checkpoint_id=latest.checkpoint_id,
                    resume_subgraph_id=subgraph_id,
                    target_nodes=list(failure.failed_nodes),
                    reason=failure.reason,
                    rollback_notify=bool(failure.failed_nodes),
                )
                self._emit(plan)
                return plan

        if prefer_node and failure.node_id:
            plan = RecoveryPlan(
                workflow_id=failure.workflow_id,
                execution_id=failure.execution_id,
                strategy=RecoveryStrategy.RESUME_NODE,
                checkpoint_id=latest.checkpoint_id,
                resume_node_id=failure.node_id,
                target_nodes=[failure.node_id],
                reason=failure.reason,
                rollback_notify=True,
            )
            self._emit(plan)
            return plan

        if failure.failed_nodes and not latest.execution_snapshot:
            plan = RecoveryPlan(
                workflow_id=failure.workflow_id,
                execution_id=failure.execution_id,
                strategy=RecoveryStrategy.ROLLBACK_NOTIFY,
                checkpoint_id=latest.checkpoint_id,
                target_nodes=list(failure.failed_nodes),
                reason=failure.reason,
                rollback_notify=True,
            )
            self._emit(plan)
            return plan

        if latest.checkpoint_id:
            plan = RecoveryPlan(
                workflow_id=failure.workflow_id,
                execution_id=failure.execution_id,
                strategy=RecoveryStrategy.RESUME_CHECKPOINT,
                checkpoint_id=latest.checkpoint_id,
                target_nodes=list(
                    latest.execution_snapshot.completed_nodes
                    if latest.execution_snapshot
                    else failure.completed_nodes
                ),
                reason=failure.reason or "resume_from_latest_checkpoint",
                rollback_notify=bool(failure.failed_nodes),
            )
            self._emit(plan)
            return plan

        raise RecoveryPlanningError("unable to produce recovery plan")

    def _emit(self, plan: RecoveryPlan) -> None:
        self.metrics.incr("recovery_count")
        self.events.emit(
            RecoveryPlanned(
                workflow_id=plan.workflow_id,
                execution_id=plan.execution_id,
                plan_id=plan.plan_id,
                strategy=plan.strategy.value,
                checkpoint_id=plan.checkpoint_id or "",
            )
        )
