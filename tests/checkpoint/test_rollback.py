"""Rollback metadata tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.checkpoint import (
    FailureContext,
    RollbackPlanningError,
)

from .conftest import fresh_manager, make_checkpoint


def test_rollback_plan_with_checkpoint() -> None:
    mgr = fresh_manager()
    stored = mgr.checkpoint(make_checkpoint())
    rec = mgr.plan_rollback(
        FailureContext(
            workflow_id="wf_test",
            execution_id="ex_test",
            failed_nodes=["n_2"],
            reason="fail",
        ),
        checkpoint_id=stored.checkpoint_id,
    )
    assert rec.target_checkpoint == stored.checkpoint_id
    assert rec.target_nodes == ["n_2"]
    hist = mgr.rollback_history("ex_test", workflow_id="wf_test")
    assert hist.depth == 1


def test_rollback_requires_target_or_checkpoint() -> None:
    mgr = fresh_manager()
    with pytest.raises(RollbackPlanningError):
        mgr.plan_rollback(
            FailureContext(workflow_id="wf", execution_id="ex", failed_nodes=[])
        )
