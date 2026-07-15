"""Preflight validation for rollback operations and plans."""

from __future__ import annotations

from typing import Any, Mapping

from .consistency import ConsistencyChecker
from .events import EventBus, RollbackValidated
from .exceptions import ChecksumMismatchError, ValidationError
from .interfaces import (
    ICheckpointRollbackPort,
    IExperienceStoreRollbackPort,
    IRecoveryPlannerPort,
    ISwarmContextRollbackPort,
    ITaskGraphRollbackPort,
)
from .metrics import RollbackMetrics
from .models import ConsistencyReport
from .recovery import RollbackPlan
from .rollback import RollbackOperation
from .snapshots import RollbackSnapshotBundle
from .versioning import SCHEMA_VERSION


class RollbackValidator:
    """Validate checkpoint exists, recovery plan, graph/context/metadata, versions."""

    def __init__(
        self,
        *,
        events: EventBus | None = None,
        metrics: RollbackMetrics | None = None,
        consistency: ConsistencyChecker | None = None,
        checkpoint_port: ICheckpointRollbackPort | None = None,
        recovery_port: IRecoveryPlannerPort | None = None,
        task_graph_port: ITaskGraphRollbackPort | None = None,
        context_port: ISwarmContextRollbackPort | None = None,
        experience_port: IExperienceStoreRollbackPort | None = None,
        require_checkpoint: bool = False,
        require_recovery_plan: bool = False,
    ) -> None:
        self.events = events or EventBus()
        self.metrics = metrics or RollbackMetrics()
        self.consistency = consistency or ConsistencyChecker(
            checkpoint_port=checkpoint_port,
            recovery_port=recovery_port,
            task_graph_port=task_graph_port,
            context_port=context_port,
            experience_port=experience_port,
        )
        self.checkpoint_port = checkpoint_port
        self.recovery_port = recovery_port
        self.require_checkpoint = require_checkpoint
        self.require_recovery_plan = require_recovery_plan

    def validate(
        self,
        target: RollbackOperation | RollbackPlan | Mapping[str, Any],
        *,
        snapshots: RollbackSnapshotBundle | None = None,
        known_nodes: list[str] | None = None,
        raise_on_error: bool = True,
    ) -> ConsistencyReport:
        data = self._as_dict(target)
        rollback_id = str(data.get("rollback_id") or data.get("plan_id") or "")

        if isinstance(target, RollbackOperation):
            if target.checksum and not target.verify_checksum():
                self.metrics.incr("validation_failures")
                if raise_on_error:
                    raise ChecksumMismatchError(target.rollback_id)
                return ConsistencyReport(ok=False)

        self._validate_required_fields(data)
        self._validate_refs(data)

        report = self.consistency.check(
            target,
            snapshots=snapshots,
            known_nodes=known_nodes,
            schema_version=SCHEMA_VERSION,
        )
        if not report.ok:
            self.metrics.incr("validation_failures")
            self.metrics.incr("consistency_violations", len(report.violations))
            if raise_on_error:
                msgs = "; ".join(v.message for v in report.violations)
                raise ValidationError(msgs)

        if rollback_id:
            self.events.emit(
                RollbackValidated(
                    rollback_id,
                    workflow_id=data.get("workflow_id"),
                    execution_id=data.get("execution_id"),
                    ok=report.ok,
                    violation_count=report.violation_count,
                )
            )
        return report

    def _as_dict(self, target: Any) -> dict[str, Any]:
        if isinstance(target, (RollbackOperation, RollbackPlan)):
            return target.model_dump(mode="python")
        return dict(target)

    def _validate_required_fields(self, data: Mapping[str, Any]) -> None:
        if not data.get("workflow_id"):
            self.metrics.incr("validation_failures")
            raise ValidationError("workflow_id required", field="workflow_id")
        if not data.get("execution_id"):
            self.metrics.incr("validation_failures")
            raise ValidationError("execution_id required", field="execution_id")

    def _validate_refs(self, data: Mapping[str, Any]) -> None:
        if self.require_checkpoint and not data.get("checkpoint_reference"):
            self.metrics.incr("validation_failures")
            raise ValidationError(
                "checkpoint_reference required", field="checkpoint_reference"
            )
        if self.require_recovery_plan and not data.get("recovery_plan_reference"):
            self.metrics.incr("validation_failures")
            raise ValidationError(
                "recovery_plan_reference required",
                field="recovery_plan_reference",
            )
        ckpt = data.get("checkpoint_reference")
        if ckpt and self.checkpoint_port is not None:
            if not self.checkpoint_port.checkpoint_exists(str(ckpt)):
                self.metrics.incr("validation_failures")
                raise ValidationError(
                    f"checkpoint does not exist: {ckpt}",
                    field="checkpoint_reference",
                )
        rplan = data.get("recovery_plan_reference")
        if rplan and self.recovery_port is not None:
            if not self.recovery_port.recovery_plan_exists(str(rplan)):
                self.metrics.incr("validation_failures")
                raise ValidationError(
                    f"recovery plan does not exist: {rplan}",
                    field="recovery_plan_reference",
                )
