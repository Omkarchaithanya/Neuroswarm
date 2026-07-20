"""Checkpoint coordination via ICheckpointManagerPort — no durable I/O ownership."""

from __future__ import annotations

from typing import Any

from .events import CheckpointCreated, CheckpointRestored, EventBus
from .exceptions import CheckpointCoordinationError
from .interfaces import ICheckpointManagerPort, IExperienceStorePort
from .lifecycle import WorkflowLifecycle
from .metrics import OrchestratorMetrics
from .models import CheckpointHandle, WorkflowExecution
from .serializer import dumps, loads
from .workflow_state import WorkflowStatus
from ._utils import new_id


class CheckpointCoordinator:
    """Coordinate checkpoint create / restore. Persistence via injected ports."""

    def __init__(
        self,
        *,
        checkpoint_manager: ICheckpointManagerPort | None = None,
        experience_store: IExperienceStorePort | None = None,
        events: EventBus | None = None,
        metrics: OrchestratorMetrics | None = None,
        lifecycle: WorkflowLifecycle | None = None,
    ) -> None:
        self.checkpoint_manager = checkpoint_manager
        self.experience_store = experience_store
        self.events = events
        self.metrics = metrics
        self.lifecycle = lifecycle or WorkflowLifecycle()

    def create(self, execution: WorkflowExecution) -> CheckpointHandle:
        # Mark checkpointed before dump so restore snapshots have a valid status.
        self.lifecycle.mark_checkpointed(execution)
        snapshot_payload: dict[str, Any] = {
            "execution_json": dumps(execution, indent=None),
            "completed_nodes": list(execution.completed_nodes),
            "failed_nodes": list(execution.failed_nodes),
            "skipped_nodes": list(execution.skipped_nodes),
        }
        snapshot_ref: str | None = None
        if self.experience_store is not None:
            snapshot_ref = self.experience_store.store_snapshot(snapshot_payload)

        metadata = {
            "execution_id": execution.execution_id,
            "workflow_id": execution.workflow_id,
            "completed_nodes": list(execution.completed_nodes),
            "snapshot_ref": snapshot_ref,
        }
        if self.checkpoint_manager is not None:
            checkpoint_id = self.checkpoint_manager.create(metadata)
        else:
            checkpoint_id = new_id("ckpt_")

        handle = CheckpointHandle(
            checkpoint_id=checkpoint_id,
            execution_id=execution.execution_id,
            snapshot_ref=snapshot_ref,
            completed_nodes=list(execution.completed_nodes),
            metadata=metadata,
        )
        execution.checkpoint_reference = checkpoint_id
        execution.metrics.checkpoint_count += 1
        if self.metrics is not None:
            self.metrics.record_checkpoint()
        if self.events is not None:
            self.events.emit(
                CheckpointCreated(
                    execution.workflow_id,
                    execution.execution_id,
                    checkpoint_id=checkpoint_id,
                )
            )
        return handle

    def restore(
        self, execution: WorkflowExecution, checkpoint_id: str
    ) -> WorkflowExecution:
        payload: Any = None
        if self.checkpoint_manager is not None:
            payload = self.checkpoint_manager.restore(checkpoint_id)
        if payload is None and self.experience_store is not None:
            try:
                payload = self.experience_store.load_snapshot(checkpoint_id)
            except Exception as exc:  # noqa: BLE001
                raise CheckpointCoordinationError(
                    f"restore failed: {exc}", checkpoint_id=checkpoint_id
                ) from exc

        if isinstance(payload, dict) and "execution_json" in payload:
            restored = loads(payload["execution_json"])
            restored.checkpoint_reference = checkpoint_id
            # Older snapshots may still say RUNNING; normalize for restore.
            if restored.status == WorkflowStatus.RUNNING:
                restored.status = WorkflowStatus.CHECKPOINTED
            self.lifecycle.mark_restored(restored)
            try:
                self.lifecycle.mark_ready(restored)
            except Exception:  # noqa: BLE001
                pass
            if self.events is not None:
                self.events.emit(
                    CheckpointRestored(
                        restored.workflow_id,
                        restored.execution_id,
                        checkpoint_id=checkpoint_id,
                    )
                )
            return restored

        execution.checkpoint_reference = checkpoint_id
        if execution.status == WorkflowStatus.RUNNING:
            execution.status = WorkflowStatus.CHECKPOINTED
        self.lifecycle.mark_restored(execution)
        if self.events is not None:
            self.events.emit(
                CheckpointRestored(
                    execution.workflow_id,
                    execution.execution_id,
                    checkpoint_id=checkpoint_id,
                )
            )
        return execution
