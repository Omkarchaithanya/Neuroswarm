"""Builder + RollbackOperation unit tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.rollback import (
    RollbackBuilder,
    RollbackLevel,
    RollbackStrategyKind,
)

from .conftest import make_operation


def test_builder_fluent():
    op = (
        RollbackBuilder()
        .workflow("wf_a", execution_id="ex_a")
        .checkpoint("ckpt_a")
        .strategy(RollbackStrategyKind.RESTART_NODE)
        .level(RollbackLevel.NODE)
        .reason("timeout")
        .node("n_9")
        .targets("n_9")
        .build()
    )
    assert op.workflow_id == "wf_a"
    assert op.execution_id == "ex_a"
    assert op.checkpoint_reference == "ckpt_a"
    assert op.rollback_strategy == RollbackStrategyKind.RESTART_NODE
    assert op.target_node == "n_9"
    assert op.checksum
    assert op.verify_checksum()


def test_builder_requires_ids():
    with pytest.raises(ValueError, match="workflow_id"):
        RollbackBuilder().execution("ex").build()
    with pytest.raises(ValueError, match="execution_id"):
        RollbackBuilder().workflow("wf").build()


def test_checksum_stable():
    op = make_operation(rollback_id="rb_fixed")
    assert op.verify_checksum()
    assert op.content_hash() == op.checksum


def test_with_status_rehashes():
    op = make_operation()
    updated = op.with_status(op.status)
    # same status still rebuilds checksum path
    assert updated.verify_checksum()
