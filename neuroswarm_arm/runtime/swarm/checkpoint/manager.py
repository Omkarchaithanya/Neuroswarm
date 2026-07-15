"""CheckpointManager facade + build_checkpoint_manager() DI factory.

Fault-Tolerance Kernel — observes execution, creates immutable recovery points,
plans resume / rollback. Does not execute workflows.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Mapping

from ._utils import estimate_size_bytes, new_id
from .budget_snapshot import BudgetSnapshot
from .cache import CheckpointCache
from .checkpoint import Checkpoint, CheckpointBuilder
from .context_snapshot import ContextSnapshot
from .events import CheckpointCreated, CheckpointRestored, EventBus
from .exceptions import NotFoundError, ValidationError
from .execution_snapshot import ExecutionSnapshot
from .graph_snapshot import GraphSnapshot
from .interfaces import (
    ICheckpointExperiencePort,
    ICheckpointManagerPort,
    IExperienceStorePort,
)
from .metrics import CheckpointMetrics
from .models import (
    CheckpointLevel,
    FailureContext,
    WorkflowObservation,
)
from .planner import RecoveryPlanner
from .policy import CheckpointPolicy, PolicyEngine
from .recovery import RecoveryPlan
from .repository import ICheckpointRepository, InMemoryRepository, JsonlRepository
from .retention import RetentionManager, RetentionPolicy
from .rollback import RollbackHistory, RollbackMetadataBuilder, RollbackRecord
from .serializer import CheckpointSerializer
from .snapshot import MetricsSnapshot
from .validator import CheckpointValidator


class CheckpointManager:
    """Production Fault-Tolerance Kernel for NEXUS-ARM swarm workflows.

    Implements ``ICheckpointManagerPort.create`` / ``restore`` for Meta Orchestrator
    injection. Extra APIs cover planning, policies, retention, and fluent builders.
    """

    def __init__(
        self,
        repository: ICheckpointRepository | None = None,
        *,
        events: EventBus | None = None,
        metrics: CheckpointMetrics | None = None,
        cache: CheckpointCache | None = None,
        experience_port: ICheckpointExperiencePort | None = None,
        experience_store: IExperienceStorePort | None = None,
        policies: list[CheckpointPolicy] | None = None,
    ) -> None:
        self.events = events or EventBus()
        self.metrics = metrics or CheckpointMetrics()
        self.repository = repository or InMemoryRepository()
        self.cache = cache or CheckpointCache()
        self.experience_port = experience_port
        self.experience_store = experience_store
        self.serializer = CheckpointSerializer()
        self.validator = CheckpointValidator(events=self.events, metrics=self.metrics)
        self.policy_engine = PolicyEngine(
            policies, events=self.events, metrics=self.metrics
        )
        self.planner = RecoveryPlanner(events=self.events, metrics=self.metrics)
        self.rollback = RollbackMetadataBuilder(events=self.events, metrics=self.metrics)
        self.retention = RetentionManager(
            self.repository, events=self.events, metrics=self.metrics
        )

    # ---- ICheckpointManagerPort ----
    def create(self, metadata: Any) -> str:
        """Create durable checkpoint from coordinator metadata; return checkpoint_id."""
        data = self.validator.validate_create_metadata(
            metadata if isinstance(metadata, Mapping) else {}
        )
        completed = list(data.get("completed_nodes") or [])
        snapshot_ref = data.get("snapshot_ref")
        parent = None
        latest = self.repository.latest_for_execution(str(data["execution_id"]))
        if latest is not None:
            parent = latest.checkpoint_id

        execution_snapshot = ExecutionSnapshot(
            execution_id=str(data["execution_id"]),
            workflow_id=str(data["workflow_id"]),
            completed_nodes=completed,
            failed_nodes=list(data.get("failed_nodes") or []),
            skipped_nodes=list(data.get("skipped_nodes") or []),
            experience_snapshot_ref=snapshot_ref,
            execution_json_ref=snapshot_ref,
            metadata={
                k: v
                for k, v in data.items()
                if k
                not in {
                    "execution_id",
                    "workflow_id",
                    "completed_nodes",
                    "failed_nodes",
                    "skipped_nodes",
                    "snapshot_ref",
                }
            },
        )
        level = data.get("checkpoint_level")
        if isinstance(level, str):
            try:
                checkpoint_level = CheckpointLevel(level)
            except ValueError:
                checkpoint_level = CheckpointLevel.AUTOMATIC
        elif isinstance(level, CheckpointLevel):
            checkpoint_level = level
        else:
            checkpoint_level = CheckpointLevel.AUTOMATIC

        builder = (
            CheckpointBuilder()
            .workflow(str(data["workflow_id"]), execution_id=str(data["execution_id"]))
            .execution(snapshot=execution_snapshot)
            .level(checkpoint_level)
            .parent(parent)
            .experience(snapshot_ref)
            .metadata(**{k: v for k, v in data.items() if k not in {"metadata"}})
        )
        if isinstance(data.get("metadata"), dict):
            builder.metadata(**data["metadata"])
        checkpoint = builder.build()
        return self.checkpoint(checkpoint).checkpoint_id

    def restore(self, checkpoint_id: str) -> Any:
        """Restore payload for CheckpointCoordinator (execution_json when available)."""
        t0 = time.perf_counter()
        cached = self.cache.get_checkpoint(checkpoint_id)
        checkpoint = cached or self.repository.get(checkpoint_id)
        self.validator.validate_checkpoint(checkpoint)
        self.cache.put_checkpoint(checkpoint)
        self.cache.put_validation(checkpoint_id, True)

        payload: dict[str, Any] = {
            "checkpoint_id": checkpoint.checkpoint_id,
            "workflow_id": checkpoint.workflow_id,
            "execution_id": checkpoint.execution_id,
            "completed_nodes": list(
                checkpoint.execution_snapshot.completed_nodes
                if checkpoint.execution_snapshot
                else []
            ),
            "experience_reference": checkpoint.experience_reference,
            "metadata": dict(checkpoint.metadata),
        }

        snap_ref = checkpoint.experience_reference
        if checkpoint.execution_snapshot and checkpoint.execution_snapshot.execution_json_ref:
            snap_ref = checkpoint.execution_snapshot.execution_json_ref

        if snap_ref and self.experience_store is not None:
            try:
                blob = self.experience_store.load_snapshot(snap_ref)
                if isinstance(blob, dict):
                    payload.update(blob)
            except Exception:  # noqa: BLE001
                # Fall back to metadata-only restore
                pass

        self.metrics.incr("restores_total")
        latency_ms = (time.perf_counter() - t0) * 1000.0
        self.metrics.record_recovery_latency(latency_ms)
        self.events.emit(
            CheckpointRestored(
                checkpoint.checkpoint_id,
                workflow_id=checkpoint.workflow_id,
                execution_id=checkpoint.execution_id,
                latency_ms=latency_ms,
            )
        )
        return payload

    # ---- rich APIs ----
    def checkpoint(self, checkpoint: Checkpoint) -> Checkpoint:
        """Validate, persist, cache, emit, and optionally attach experience refs."""
        self.validator.validate_checkpoint(checkpoint)
        stored = self.repository.append(checkpoint)
        self.cache.put_checkpoint(stored)
        self.cache.put_validation(stored.checkpoint_id, True)

        size = estimate_size_bytes(stored.model_dump(mode="json"))
        self.metrics.incr("checkpoint_count")
        self.metrics.incr("checkpoint_size_bytes", size)
        snap_n = sum(
            1
            for s in (
                stored.execution_snapshot,
                stored.context_snapshot,
                stored.budget_snapshot,
                stored.metrics_snapshot,
                stored.graph_snapshot,
            )
            if s is not None
        )
        if snap_n:
            self.metrics.incr("snapshot_count", snap_n)

        self.events.emit(
            CheckpointCreated(
                stored.checkpoint_id,
                workflow_id=stored.workflow_id,
                execution_id=stored.execution_id,
                level=stored.checkpoint_level.value,
                size_bytes=size,
            )
        )
        if self.experience_port is not None:
            self.experience_port.attach_checkpoint_refs(
                stored.execution_id, [stored.checkpoint_id]
            )
        return stored

    def get(self, checkpoint_id: str) -> Checkpoint:
        cached = self.cache.get_checkpoint(checkpoint_id)
        if cached is not None:
            return cached
        ckpt = self.repository.get(checkpoint_id)
        self.cache.put_checkpoint(ckpt)
        return ckpt

    def list_workflow(
        self, workflow_id: str, *, include_archived: bool = False
    ) -> list[Checkpoint]:
        return self.repository.list_by_workflow(
            workflow_id, include_archived=include_archived
        )

    def list_execution(
        self, execution_id: str, *, include_archived: bool = False
    ) -> list[Checkpoint]:
        return self.repository.list_by_execution(
            execution_id, include_archived=include_archived
        )

    def latest(self, *, execution_id: str | None = None, workflow_id: str | None = None) -> Checkpoint | None:
        if execution_id:
            cached = self.cache.latest_for_execution(execution_id)
            if cached is not None:
                return cached
            return self.repository.latest_for_execution(execution_id)
        if workflow_id:
            cached = self.cache.latest_for_workflow(workflow_id)
            if cached is not None:
                return cached
            return self.repository.latest_for_workflow(workflow_id)
        raise ValidationError("execution_id or workflow_id required", field="id")

    def evaluate_policy(self, observation: WorkflowObservation) -> bool:
        return self.policy_engine.should_checkpoint(observation)

    def maybe_checkpoint(
        self,
        observation: WorkflowObservation,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> str | None:
        if not self.evaluate_policy(observation):
            return None
        meta = {
            "workflow_id": observation.workflow_id,
            "execution_id": observation.execution_id,
            "completed_nodes": list(observation.completed_nodes),
            **dict(metadata or {}),
        }
        return self.create(meta)

    def plan_recovery(
        self,
        failure: FailureContext,
        *,
        prefer_node: bool = False,
        prefer_subgraph: bool = False,
    ) -> RecoveryPlan:
        cache_key = (
            f"{failure.execution_id}:{failure.reason}:{prefer_node}:{prefer_subgraph}"
        )
        cached = self.cache.get_recovery_plan(cache_key)
        if cached is not None:
            return cached
        checkpoints = self.repository.list_by_execution(failure.execution_id)
        plan = self.planner.plan(
            failure,
            checkpoints,
            prefer_node=prefer_node,
            prefer_subgraph=prefer_subgraph,
        )
        self.cache.put_recovery_plan(cache_key, plan)
        return plan

    def plan_rollback(
        self,
        failure: FailureContext,
        *,
        checkpoint_id: str | None = None,
        target_nodes: list[str] | None = None,
    ) -> RollbackRecord:
        ckpt = None
        if checkpoint_id:
            ckpt = self.get(checkpoint_id)
        elif failure.execution_id:
            ckpt = self.repository.latest_for_execution(failure.execution_id)
        return self.rollback.plan(
            failure, checkpoint=ckpt, target_nodes=target_nodes
        )

    def rollback_history(self, execution_id: str, workflow_id: str = "") -> RollbackHistory:
        return self.rollback.history(execution_id, workflow_id=workflow_id)

    def apply_retention(self, policy: RetentionPolicy) -> dict[str, Any]:
        return self.retention.apply(policy)

    def builder(self) -> CheckpointBuilder:
        return CheckpointBuilder()

    async def acreate(self, metadata: Any) -> str:
        return self.create(metadata)

    async def arestore(self, checkpoint_id: str) -> Any:
        return self.restore(checkpoint_id)


def build_checkpoint_manager(
    *,
    repository: ICheckpointRepository | None = None,
    path: str | Path | None = None,
    events: EventBus | None = None,
    metrics: CheckpointMetrics | None = None,
    cache: CheckpointCache | None = None,
    experience_port: ICheckpointExperiencePort | None = None,
    experience_store: IExperienceStorePort | None = None,
    policies: list[CheckpointPolicy] | None = None,
) -> CheckpointManager:
    """Composition-root factory for CheckpointManager."""
    repo = repository
    if repo is None and path is not None:
        repo = JsonlRepository(path)
    return CheckpointManager(
        repository=repo,
        events=events,
        metrics=metrics,
        cache=cache,
        experience_port=experience_port,
        experience_store=experience_store,
        policies=policies,
    )


# Re-export for typing convenience
__all__ = [
    "CheckpointManager",
    "build_checkpoint_manager",
    "ICheckpointManagerPort",
    "Checkpoint",
    "CheckpointBuilder",
    "BudgetSnapshot",
    "ContextSnapshot",
    "ExecutionSnapshot",
    "GraphSnapshot",
    "MetricsSnapshot",
    "new_id",
    "NotFoundError",
]
