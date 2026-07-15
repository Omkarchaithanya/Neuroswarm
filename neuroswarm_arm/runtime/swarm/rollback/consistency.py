"""Consistency validation — graph / exec / ckpt / context / budget / artifacts."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ._utils import utc_now
from .interfaces import (
    ICheckpointRollbackPort,
    IExperienceStoreRollbackPort,
    IRecoveryPlannerPort,
    ISwarmContextRollbackPort,
    ITaskGraphRollbackPort,
)
from .models import (
    ConsistencyReport,
    ConsistencyViolation,
    ConsistencyViolationKind,
)
from .recovery import RollbackPlan
from .rollback import RollbackOperation
from .snapshots import RollbackSnapshotBundle
from .versioning import SCHEMA_VERSION


class ConsistencyChecker:
    """Detect orphan nodes, invalid checkpoints, version mismatch, partial failures."""

    def __init__(
        self,
        *,
        checkpoint_port: ICheckpointRollbackPort | None = None,
        recovery_port: IRecoveryPlannerPort | None = None,
        task_graph_port: ITaskGraphRollbackPort | None = None,
        context_port: ISwarmContextRollbackPort | None = None,
        experience_port: IExperienceStoreRollbackPort | None = None,
    ) -> None:
        self.checkpoint_port = checkpoint_port
        self.recovery_port = recovery_port
        self.task_graph_port = task_graph_port
        self.context_port = context_port
        self.experience_port = experience_port

    def check(
        self,
        target: RollbackOperation | RollbackPlan | Mapping[str, Any],
        *,
        snapshots: RollbackSnapshotBundle | None = None,
        known_nodes: Sequence[str] | None = None,
        schema_version: int | None = None,
    ) -> ConsistencyReport:
        violations: list[ConsistencyViolation] = []
        data = self._as_dict(target)

        violations.extend(self._check_checkpoint(data))
        violations.extend(self._check_recovery_plan(data))
        violations.extend(self._check_version(data, schema_version))
        violations.extend(self._check_graph(data, snapshots, known_nodes))
        violations.extend(self._check_execution(data, snapshots))
        violations.extend(self._check_context(data, snapshots))
        violations.extend(self._check_budget(data, snapshots))
        violations.extend(self._check_artifacts(data, snapshots))
        violations.extend(self._check_experience(snapshots))
        violations.extend(self._check_partial_failure(data, snapshots))

        return ConsistencyReport(
            ok=len(violations) == 0,
            violations=violations,
            checked_at=utc_now(),
            metadata={"checks": 10},
        )

    def _as_dict(self, target: Any) -> dict[str, Any]:
        if isinstance(target, (RollbackOperation, RollbackPlan)):
            return target.model_dump(mode="python")
        return dict(target)

    def _check_checkpoint(self, data: Mapping[str, Any]) -> list[ConsistencyViolation]:
        ref = data.get("checkpoint_reference")
        if not ref:
            return []
        if self.checkpoint_port is None:
            return []
        if not self.checkpoint_port.checkpoint_exists(str(ref)):
            return [
                ConsistencyViolation(
                    kind=ConsistencyViolationKind.INVALID_CHECKPOINT,
                    message=f"checkpoint not found: {ref}",
                    path="checkpoint_reference",
                )
            ]
        return []

    def _check_recovery_plan(
        self, data: Mapping[str, Any]
    ) -> list[ConsistencyViolation]:
        ref = data.get("recovery_plan_reference")
        if not ref or self.recovery_port is None:
            return []
        if not self.recovery_port.recovery_plan_exists(str(ref)):
            return [
                ConsistencyViolation(
                    kind=ConsistencyViolationKind.INVALID_CHECKPOINT,
                    message=f"recovery plan not found: {ref}",
                    path="recovery_plan_reference",
                )
            ]
        return []

    def _check_version(
        self, data: Mapping[str, Any], schema_version: int | None
    ) -> list[ConsistencyViolation]:
        expected = schema_version if schema_version is not None else SCHEMA_VERSION
        found = data.get("version", expected)
        try:
            found_i = int(found)
        except (TypeError, ValueError):
            return [
                ConsistencyViolation(
                    kind=ConsistencyViolationKind.VERSION_MISMATCH,
                    message=f"invalid version value: {found}",
                    path="version",
                )
            ]
        if found_i != expected:
            return [
                ConsistencyViolation(
                    kind=ConsistencyViolationKind.VERSION_MISMATCH,
                    message=f"version mismatch: found={found_i} expected={expected}",
                    path="version",
                )
            ]
        return []

    def _check_graph(
        self,
        data: Mapping[str, Any],
        snapshots: RollbackSnapshotBundle | None,
        known_nodes: Sequence[str] | None,
    ) -> list[ConsistencyViolation]:
        nodes: set[str] = set()
        if known_nodes is not None:
            nodes.update(known_nodes)
        elif self.task_graph_port is not None:
            nodes.update(self.task_graph_port.node_ids())
        elif snapshots and snapshots.graph:
            nodes.update(snapshots.graph.completed_nodes)
            nodes.update(snapshots.graph.frontier_nodes)
            nodes.update(snapshots.graph.failed_nodes)

        if not nodes:
            return []

        violations: list[ConsistencyViolation] = []
        targets = list(data.get("target_nodes") or [])
        if data.get("target_node"):
            targets.append(str(data["target_node"]))
        for node in targets:
            if node not in nodes:
                violations.append(
                    ConsistencyViolation(
                        kind=ConsistencyViolationKind.ORPHAN_NODE,
                        message=f"orphan / unknown target node: {node}",
                        path="target_nodes",
                        metadata={"node_id": node},
                    )
                )
                violations.append(
                    ConsistencyViolation(
                        kind=ConsistencyViolationKind.GRAPH_INCONSISTENT,
                        message=f"graph missing node: {node}",
                        path="target_nodes",
                    )
                )
        return violations

    def _check_execution(
        self,
        data: Mapping[str, Any],
        snapshots: RollbackSnapshotBundle | None,
    ) -> list[ConsistencyViolation]:
        if snapshots is None or snapshots.execution is None:
            return []
        if snapshots.execution.execution_id != data.get("execution_id"):
            return [
                ConsistencyViolation(
                    kind=ConsistencyViolationKind.EXECUTION_INCONSISTENT,
                    message="execution snapshot id mismatch",
                    path="execution_id",
                )
            ]
        return []

    def _check_context(
        self,
        data: Mapping[str, Any],
        snapshots: RollbackSnapshotBundle | None,
    ) -> list[ConsistencyViolation]:
        ctx = data.get("target_context")
        if not ctx:
            return []
        if self.context_port is not None:
            snap_id = self.context_port.latest_snapshot_id(str(ctx))
            if snap_id is None and (
                snapshots is None
                or snapshots.context is None
                or snapshots.context.context_id != ctx
            ):
                return [
                    ConsistencyViolation(
                        kind=ConsistencyViolationKind.CONTEXT_INCONSISTENT,
                        message=f"context snapshot missing: {ctx}",
                        path="target_context",
                    )
                ]
        if snapshots and snapshots.context and snapshots.context.context_id != ctx:
            return [
                ConsistencyViolation(
                    kind=ConsistencyViolationKind.CONTEXT_INCONSISTENT,
                    message="context snapshot id mismatch",
                    path="target_context",
                )
            ]
        return []

    def _check_budget(
        self,
        data: Mapping[str, Any],
        snapshots: RollbackSnapshotBundle | None,
    ) -> list[ConsistencyViolation]:
        budget = data.get("target_budget")
        if not budget:
            return []
        if snapshots and snapshots.budget and snapshots.budget.envelope_id != budget:
            return [
                ConsistencyViolation(
                    kind=ConsistencyViolationKind.BUDGET_INCONSISTENT,
                    message="budget envelope id mismatch",
                    path="target_budget",
                )
            ]
        return []

    def _check_artifacts(
        self,
        data: Mapping[str, Any],
        snapshots: RollbackSnapshotBundle | None,
    ) -> list[ConsistencyViolation]:
        refs = list(data.get("artifact_refs") or [])
        if snapshots:
            refs.extend(snapshots.artifacts)
        violations: list[ConsistencyViolation] = []
        for ref in refs:
            aid = ref.artifact_id if hasattr(ref, "artifact_id") else ref.get("artifact_id")
            if not aid:
                violations.append(
                    ConsistencyViolation(
                        kind=ConsistencyViolationKind.ARTIFACT_DANGLING,
                        message="artifact missing artifact_id",
                        path="artifact_refs",
                    )
                )
        return violations

    def _check_experience(
        self, snapshots: RollbackSnapshotBundle | None
    ) -> list[ConsistencyViolation]:
        if snapshots is None or not snapshots.experience_refs:
            return []
        if self.experience_port is None:
            return []
        violations: list[ConsistencyViolation] = []
        for eid in snapshots.experience_refs:
            if not self.experience_port.experience_exists(eid):
                violations.append(
                    ConsistencyViolation(
                        kind=ConsistencyViolationKind.EXPERIENCE_DANGLING,
                        message=f"experience ref missing: {eid}",
                        path="experience_refs",
                        metadata={"experience_id": eid},
                    )
                )
        return violations

    def _check_partial_failure(
        self,
        data: Mapping[str, Any],
        snapshots: RollbackSnapshotBundle | None,
    ) -> list[ConsistencyViolation]:
        failed = list(data.get("target_nodes") or [])
        if snapshots and snapshots.execution:
            failed = failed or list(snapshots.execution.failed_nodes)
        completed = set()
        if snapshots and snapshots.execution:
            completed = set(snapshots.execution.completed_nodes)
        # Partial failure: overlap of failed and completed without checkpoint
        overlap = completed.intersection(failed)
        if overlap and not data.get("checkpoint_reference"):
            return [
                ConsistencyViolation(
                    kind=ConsistencyViolationKind.PARTIAL_FAILURE,
                    message=f"partial failure without checkpoint: {sorted(overlap)}",
                    path="target_nodes",
                )
            ]
        return []
