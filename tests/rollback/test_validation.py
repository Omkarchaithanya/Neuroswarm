"""Validation tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.rollback import (
    ValidationError,
    build_rollback_manager,
)

from .conftest import FakeCheckpointPort, make_failure, make_operation


def test_validate_operation_ok():
    mgr = build_rollback_manager(
        checkpoint_port=FakeCheckpointPort({"ckpt_test"}),
    )
    op = make_operation()
    report = mgr.validate(op, known_nodes=["n_1", "n_2"])
    assert report.ok


def test_validate_missing_checkpoint():
    mgr = build_rollback_manager(
        checkpoint_port=FakeCheckpointPort(set()),
        require_checkpoint=True,
    )
    op = make_operation(checkpoint_reference="missing")
    with pytest.raises(ValidationError):
        mgr.validate(op)


def test_validate_orphan_node():
    mgr = build_rollback_manager()
    plan = mgr.plan(make_failure(failed_nodes=["ghost"], node_id="ghost"))
    with pytest.raises(ValidationError, match="orphan"):
        mgr.validate(plan, known_nodes=["n_1", "n_2"])


def test_checksum_mismatch():
    from neuroswarm_arm.runtime.swarm.rollback import (
        ChecksumMismatchError,
        RollbackValidator,
    )

    op = make_operation()
    data = op.model_dump(mode="python")
    data["checksum"] = "deadbeef"
    from neuroswarm_arm.runtime.swarm.rollback import RollbackOperation

    bad = RollbackOperation.model_validate(data)
    # bypass validator recompute by constructing with wrong checksum set
    object.__setattr__(bad, "checksum", "deadbeef")
    validator = RollbackValidator()
    with pytest.raises(ChecksumMismatchError):
        validator.validate(bad)
