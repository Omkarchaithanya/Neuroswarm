"""Validation for Experience Store records and references."""

from __future__ import annotations

from typing import Any, Iterable

from .execution_record import ExecutionRecord
from .exceptions import DuplicateIdError, ValidationError, VersionMismatchError
from .quality import QualityScore
from .workflow_record import WorkflowRecord

CURRENT_SCHEMA_VERSION = 1


def validate_execution_record(
    record: ExecutionRecord,
    *,
    existing_ids: Iterable[str] | None = None,
    expected_version: int = CURRENT_SCHEMA_VERSION,
) -> ExecutionRecord:
    """Validate an ExecutionRecord before append."""
    if not record.execution_id:
        raise ValidationError("execution_id required", field="execution_id")
    if not record.workflow_id:
        raise ValidationError("workflow_id required", field="workflow_id")
    if record.version != expected_version and record.version > expected_version:
        raise VersionMismatchError(record.version, expected_version)
    if existing_ids is not None and record.execution_id in set(existing_ids):
        raise DuplicateIdError(record.execution_id, kind="execution")
    validate_quality(record.quality_score)
    validate_metrics(record.metrics)
    if record.content_hash:
        recomputed = record.rehash()
        if recomputed != record.content_hash:
            raise ValidationError(
                "content_hash mismatch",
                field="content_hash",
            )
    _validate_refs(record)
    return record


def validate_workflow_record(
    record: WorkflowRecord,
    *,
    existing_ids: Iterable[str] | None = None,
    known_execution_ids: Iterable[str] | None = None,
) -> WorkflowRecord:
    if not record.workflow_id:
        raise ValidationError("workflow_id required", field="workflow_id")
    if existing_ids is not None and record.workflow_id in set(existing_ids):
        raise DuplicateIdError(record.workflow_id, kind="workflow")
    if known_execution_ids is not None:
        known = set(known_execution_ids)
        missing = [eid for eid in record.execution_ids if eid not in known]
        if missing:
            raise ValidationError(
                f"missing execution references: {missing}",
                field="execution_ids",
            )
    return record


def validate_quality(score: QualityScore) -> QualityScore:
    # Construction already enforces ranges; re-check overall for safety.
    if score.overall is not None and (score.overall < 0.0 or score.overall > 1.0):
        raise ValidationError("invalid quality overall", field="quality_score")
    return score


def validate_metrics(metrics: dict[str, float]) -> dict[str, float]:
    for key, value in metrics.items():
        if not isinstance(key, str) or not key:
            raise ValidationError("metric key must be non-empty str", field="metrics")
        try:
            float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                f"invalid metric value for {key}",
                field="metrics",
            ) from exc
        if float(value) != float(value):  # NaN
            raise ValidationError(f"NaN metric: {key}", field="metrics")
    return metrics


def _validate_refs(record: ExecutionRecord) -> None:
    for artifact in record.artifacts:
        if not artifact.uri:
            raise ValidationError("artifact uri required", field="artifacts")
    for cp in record.checkpoints:
        if not cp.checkpoint_id:
            raise ValidationError("checkpoint_id required", field="checkpoints")


def validate_snapshot_payload(snapshot: Any) -> Any:
    if snapshot is None:
        raise ValidationError("snapshot cannot be None", field="snapshot")
    return snapshot
