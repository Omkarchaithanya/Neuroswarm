"""Domain validation for checkpoints, policies, and snapshots."""

from __future__ import annotations

from typing import Any, Mapping

from .checkpoint import Checkpoint
from .events import EventBus, ValidationFailed
from .exceptions import ChecksumMismatchError, ValidationError
from .metrics import CheckpointMetrics
from .policy import CheckpointPolicy


class CheckpointValidator:
    """Validate checkpoint integrity and metadata shapes."""

    def __init__(
        self,
        *,
        events: EventBus | None = None,
        metrics: CheckpointMetrics | None = None,
    ) -> None:
        self.events = events or EventBus()
        self.metrics = metrics or CheckpointMetrics()

    def validate_checkpoint(self, checkpoint: Checkpoint) -> Checkpoint:
        if not checkpoint.checkpoint_id:
            self._fail(checkpoint, "checkpoint_id required", field="checkpoint_id")
        if not checkpoint.workflow_id:
            self._fail(checkpoint, "workflow_id required", field="workflow_id")
        if not checkpoint.execution_id:
            self._fail(checkpoint, "execution_id required", field="execution_id")
        if not checkpoint.verify_checksum():
            self.metrics.incr("validation_failures")
            self.events.emit(
                ValidationFailed(
                    checkpoint_id=checkpoint.checkpoint_id,
                    workflow_id=checkpoint.workflow_id,
                    execution_id=checkpoint.execution_id,
                    reason="checksum_mismatch",
                )
            )
            raise ChecksumMismatchError(checkpoint.checkpoint_id)
        self._validate_snapshots(checkpoint)
        return checkpoint

    def validate_create_metadata(self, metadata: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(metadata, Mapping):
            raise ValidationError("metadata must be a mapping", field="metadata")
        data = dict(metadata)
        if not data.get("execution_id"):
            raise ValidationError("execution_id required", field="execution_id")
        if not data.get("workflow_id"):
            raise ValidationError("workflow_id required", field="workflow_id")
        return data

    def validate_policy(self, policy: CheckpointPolicy) -> CheckpointPolicy:
        if policy.kind.value in {"every_n_nodes", "every_n_seconds"}:
            if policy.n is None or policy.n < 1:
                raise ValidationError("policy.n must be >= 1", field="n")
        if policy.kind.value == "custom" and policy.predicate is None:
            raise ValidationError("custom policy requires predicate", field="predicate")
        return policy

    def _validate_snapshots(self, checkpoint: Checkpoint) -> None:
        snaps = [
            checkpoint.execution_snapshot,
            checkpoint.context_snapshot,
            checkpoint.budget_snapshot,
            checkpoint.metrics_snapshot,
            checkpoint.graph_snapshot,
        ]
        for snap in snaps:
            if snap is None:
                continue
            content_hash = getattr(snap, "content_hash", None)
            if content_hash is None:
                self._fail(
                    checkpoint,
                    "snapshot missing content_hash",
                    field="snapshot",
                )

    def _fail(
        self,
        checkpoint: Checkpoint,
        message: str,
        *,
        field: str,
    ) -> None:
        self.metrics.incr("validation_failures")
        self.events.emit(
            ValidationFailed(
                checkpoint_id=checkpoint.checkpoint_id,
                workflow_id=checkpoint.workflow_id,
                execution_id=checkpoint.execution_id,
                reason=message,
                field=field,
            )
        )
        raise ValidationError(message, field=field)
