"""Consistency checker tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.rollback import (
    ArtifactReference,
    ConsistencyChecker,
    ConsistencyViolationKind,
    RollbackSnapshotBundle,
)

from .conftest import FakeCheckpointPort, FakeRecoveryPort, make_operation


def test_invalid_checkpoint_violation():
    checker = ConsistencyChecker(checkpoint_port=FakeCheckpointPort(set()))
    op = make_operation(checkpoint_reference="nope")
    report = checker.check(op)
    assert not report.ok
    assert any(
        v.kind == ConsistencyViolationKind.INVALID_CHECKPOINT for v in report.violations
    )


def test_version_mismatch():
    checker = ConsistencyChecker()
    op = make_operation(version=99)
    report = checker.check(op)
    assert not report.ok
    assert any(
        v.kind == ConsistencyViolationKind.VERSION_MISMATCH for v in report.violations
    )


def test_experience_dangling():
    class Exp:
        def experience_exists(self, eid: str) -> bool:
            return False

        def attach_rollback_refs(self, execution_id: str, rollback_ids: list[str]) -> None:
            pass

    checker = ConsistencyChecker(experience_port=Exp())
    snap = RollbackSnapshotBundle(experience_refs=["exp_missing"])
    report = checker.check(make_operation(), snapshots=snap)
    assert any(
        v.kind == ConsistencyViolationKind.EXPERIENCE_DANGLING for v in report.violations
    )


def test_artifact_ok():
    checker = ConsistencyChecker()
    op = make_operation()
    data = op.model_dump(mode="python")
    data["checksum"] = None
    data["artifact_refs"] = [ArtifactReference(artifact_id="a1").model_dump()]
    from neuroswarm_arm.runtime.swarm.rollback import RollbackOperation

    op2 = RollbackOperation.model_validate(data)
    report = checker.check(op2)
    assert report.ok or not any(
        v.kind == ConsistencyViolationKind.ARTIFACT_DANGLING for v in report.violations
    )


def test_recovery_plan_port():
    checker = ConsistencyChecker(recovery_port=FakeRecoveryPort(set()))
    op = make_operation(recovery_plan_reference="missing_plan")
    report = checker.check(op)
    assert not report.ok
