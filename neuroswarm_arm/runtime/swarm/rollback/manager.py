"""RollbackManager facade + build_rollback_manager() DI factory.

Runtime Transaction & Recovery subsystem — restores consistency after partial
execution failures. Does not execute workflows, schedule tasks, or run inference.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .events import EventBus, RollbackCancelled
from .exceptions import CancellationError, NotFoundError
from .execution import RollbackExecutor, RollbackResult, stamp_metadata
from .history import RollbackHistoryStore, RollbackHistoryView
from .interfaces import (
    IArmoraBudgetRollbackPort,
    ICheckpointRollbackPort,
    IExperienceStoreRollbackPort,
    IPerformixRollbackPort,
    IPolicyPredicatePort,
    IRecoveryPlannerPort,
    ISwarmContextRollbackPort,
    ITaskGraphRollbackPort,
)
from .lifecycle import can_transition
from .metadata import RollbackExecutionMetadata
from .metrics import RollbackMetrics
from .models import (
    ConsistencyReport,
    FailureObservation,
    RollbackAnalytics,
    RollbackObservation,
    RollbackStatus,
    RollbackStrategyKind,
)
from .planner import RollbackPlanner
from .policies import PolicyEngine, RollbackPolicy
from .recovery import RecoveryExecutionMetadata, RollbackPlan
from .repository import IRollbackRepository, InMemoryRepository, JsonlRepository
from .rollback import RollbackBuilder, RollbackOperation
from .serializer import RollbackSerializer
from .snapshots import RollbackSnapshotBundle
from .strategy import IRollbackStrategy
from .validator import RollbackValidator


class RollbackManager:
    """Production Rollback Manager for NEXUS-ARM swarm workflows.

    Implements ``IRollbackManagerPort.plan`` / ``validate`` / ``execute``.
    Extra APIs cover prepare, cancel, history, analytics, and fluent builders.
    """

    def __init__(
        self,
        repository: IRollbackRepository | None = None,
        *,
        events: EventBus | None = None,
        metrics: RollbackMetrics | None = None,
        policies: list[RollbackPolicy] | None = None,
        checkpoint_port: ICheckpointRollbackPort | None = None,
        recovery_port: IRecoveryPlannerPort | None = None,
        task_graph_port: ITaskGraphRollbackPort | None = None,
        context_port: ISwarmContextRollbackPort | None = None,
        budget_port: IArmoraBudgetRollbackPort | None = None,
        experience_port: IExperienceStoreRollbackPort | None = None,
        performix_port: IPerformixRollbackPort | None = None,
        predicate_port: IPolicyPredicatePort | None = None,
        require_checkpoint: bool = False,
    ) -> None:
        self.events = events or EventBus()
        self.metrics = metrics or RollbackMetrics()
        self.repository = repository or InMemoryRepository()
        self.history_store = RollbackHistoryStore()
        self.serializer = RollbackSerializer()
        self.planner = RollbackPlanner(events=self.events, metrics=self.metrics)
        self.validator = RollbackValidator(
            events=self.events,
            metrics=self.metrics,
            checkpoint_port=checkpoint_port,
            recovery_port=recovery_port,
            task_graph_port=task_graph_port,
            context_port=context_port,
            experience_port=experience_port,
            require_checkpoint=require_checkpoint,
        )
        self.executor = RollbackExecutor(
            events=self.events,
            metrics=self.metrics,
            checkpoint_port=checkpoint_port,
            context_port=context_port,
            budget_port=budget_port,
            performix_port=performix_port,
        )
        self.policy_engine = PolicyEngine(
            policies,
            events=self.events,
            metrics=self.metrics,
            predicate_port=predicate_port,
        )
        self.checkpoint_port = checkpoint_port
        self.recovery_port = recovery_port
        self.experience_port = experience_port

    # ---- IRollbackManagerPort ----
    def plan(
        self,
        observation: FailureObservation | Mapping[str, Any],
        *,
        strategy: RollbackStrategyKind | IRollbackStrategy | str | None = None,
        **kwargs: Any,
    ) -> RollbackPlan:
        return self.planner.plan(observation, strategy=strategy, **kwargs)

    def validate(
        self,
        target: RollbackOperation | RollbackPlan | Mapping[str, Any],
        *,
        snapshots: RollbackSnapshotBundle | None = None,
        known_nodes: list[str] | None = None,
        raise_on_error: bool = True,
    ) -> ConsistencyReport:
        return self.validator.validate(
            target,
            snapshots=snapshots,
            known_nodes=known_nodes,
            raise_on_error=raise_on_error,
        )

    def execute(self, plan: RollbackPlan) -> RollbackResult:
        report = self.validate(plan, raise_on_error=True)
        op = self._plan_to_operation(plan).with_status(RollbackStatus.VALIDATED)
        self.repository.append(op)
        meta = self.repository.get_metadata(op.rollback_id)
        meta = stamp_metadata(meta, RollbackStatus.VALIDATED)
        self.repository.set_metadata(meta)

        recovery = self.prepare(plan)
        meta = stamp_metadata(
            self.repository.get_metadata(op.rollback_id), RollbackStatus.PREPARED
        )
        self.repository.set_metadata(meta)
        self.repository.update_status(op.rollback_id, RollbackStatus.PREPARED)

        result = self.executor.execute(plan, recovery=recovery)
        self.repository.update_status(op.rollback_id, RollbackStatus.COMPLETED)
        meta = stamp_metadata(
            self.repository.get_metadata(op.rollback_id),
            RollbackStatus.COMPLETED,
            duration_ms=result.duration_ms,
        )
        self.repository.set_metadata(meta)
        self.history_store.record(plan=plan, result=result, success=True)
        if self.experience_port is not None:
            self.experience_port.attach_rollback_refs(
                plan.execution_id, [plan.rollback_id]
            )
        # silence unused if report unused in lint
        _ = report
        return result

    def prepare(self, plan: RollbackPlan) -> RecoveryExecutionMetadata:
        return self.executor.prepare(plan)

    def cancel(self, rollback_id: str) -> RollbackOperation:
        op = self.repository.get(rollback_id)
        if not can_transition(op.status, RollbackStatus.CANCELLED):
            raise CancellationError(
                f"cannot cancel rollback in status {op.status.value}"
            )
        updated = self.repository.update_status(rollback_id, RollbackStatus.CANCELLED)
        meta = stamp_metadata(
            self.repository.get_metadata(rollback_id), RollbackStatus.CANCELLED
        )
        self.repository.set_metadata(meta)
        self.metrics.incr("cancelled_count")
        self.events.emit(
            RollbackCancelled(
                rollback_id,
                workflow_id=op.workflow_id,
                execution_id=op.execution_id,
            )
        )
        self.history_store.record(
            operation=updated, success=False, reason="cancelled"
        )
        return updated

    def should_rollback(self, observation: RollbackObservation) -> bool:
        return self.policy_engine.should_rollback(observation)

    def history(self, execution_id: str) -> RollbackHistoryView:
        return self.history_store.for_execution(execution_id)

    def analytics(
        self,
        *,
        execution_id: str | None = None,
        workflow_id: str | None = None,
    ) -> RollbackAnalytics:
        return self.history_store.analytics(
            execution_id=execution_id, workflow_id=workflow_id
        )

    def get(self, rollback_id: str) -> RollbackOperation:
        return self.repository.get(rollback_id)

    def get_metadata(self, rollback_id: str) -> RollbackExecutionMetadata:
        return self.repository.get_metadata(rollback_id)

    def builder(self) -> RollbackBuilder:
        return RollbackBuilder()

    def register(self, operation: RollbackOperation) -> RollbackOperation:
        self.validate(operation, raise_on_error=True)
        return self.repository.append(operation)

    # ---- async thin wrappers ----
    async def aplan(
        self,
        observation: FailureObservation | Mapping[str, Any],
        **kwargs: Any,
    ) -> RollbackPlan:
        return self.plan(observation, **kwargs)

    async def avalidate(
        self,
        target: RollbackOperation | RollbackPlan | Mapping[str, Any],
        **kwargs: Any,
    ) -> ConsistencyReport:
        return self.validate(target, **kwargs)

    async def aexecute(self, plan: RollbackPlan) -> RollbackResult:
        return self.execute(plan)

    def _plan_to_operation(self, plan: RollbackPlan) -> RollbackOperation:
        return (
            RollbackBuilder()
            .rollback_id(plan.rollback_id)
            .workflow(plan.workflow_id, execution_id=plan.execution_id)
            .checkpoint(plan.checkpoint_reference)
            .recovery_plan(plan.recovery_plan_reference)
            .strategy(plan.strategy)
            .level(plan.level)
            .reason(plan.reason)
            .node(plan.target_node)
            .subgraph(plan.target_subgraph)
            .context(plan.target_context)
            .budget(plan.target_budget)
            .targets(*plan.target_nodes)
            .meta(**plan.metadata)
            .build()
        )


def build_rollback_manager(
    *,
    repository: IRollbackRepository | None = None,
    path: str | Path | None = None,
    events: EventBus | None = None,
    metrics: RollbackMetrics | None = None,
    policies: list[RollbackPolicy] | None = None,
    checkpoint_port: ICheckpointRollbackPort | None = None,
    recovery_port: IRecoveryPlannerPort | None = None,
    task_graph_port: ITaskGraphRollbackPort | None = None,
    context_port: ISwarmContextRollbackPort | None = None,
    budget_port: IArmoraBudgetRollbackPort | None = None,
    experience_port: IExperienceStoreRollbackPort | None = None,
    performix_port: IPerformixRollbackPort | None = None,
    predicate_port: IPolicyPredicatePort | None = None,
    require_checkpoint: bool = False,
) -> RollbackManager:
    """Composition-root factory for RollbackManager."""
    if repository is None and path is not None:
        repository = JsonlRepository(path)
    return RollbackManager(
        repository,
        events=events,
        metrics=metrics,
        policies=policies,
        checkpoint_port=checkpoint_port,
        recovery_port=recovery_port,
        task_graph_port=task_graph_port,
        context_port=context_port,
        budget_port=budget_port,
        experience_port=experience_port,
        performix_port=performix_port,
        predicate_port=predicate_port,
        require_checkpoint=require_checkpoint,
    )


__all__ = [
    "RollbackManager",
    "build_rollback_manager",
    "NotFoundError",
]
