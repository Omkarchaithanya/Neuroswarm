"""Execution / prepare / cancel tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.rollback import (
    CancellationError,
    RollbackStatus,
)

from .conftest import FakeCheckpointPort, fresh_manager, make_failure


def test_execute_success():
    mgr = fresh_manager(checkpoint_port=FakeCheckpointPort())
    plan = mgr.plan(make_failure())
    result = mgr.execute(plan)
    assert result.status == RollbackStatus.COMPLETED
    assert result.duration_ms >= 0.0
    assert result.recovery is not None
    assert result.recovery.rollback_depth >= 1
    stored = mgr.get(plan.rollback_id)
    assert stored.status == RollbackStatus.COMPLETED


def test_prepare_emits_recovery_metadata():
    mgr = fresh_manager()
    plan = mgr.plan(make_failure())
    meta = mgr.prepare(plan)
    assert meta.rollback_id == plan.rollback_id
    assert meta.recovery_order == plan.recovery_order
    events = [e.type for e in mgr.events.history()]
    assert "RecoveryPrepared" in events


def test_cancel_terminal_fails():
    mgr = fresh_manager(checkpoint_port=FakeCheckpointPort())
    plan = mgr.plan(make_failure())
    mgr.execute(plan)
    with pytest.raises(CancellationError):
        mgr.cancel(plan.rollback_id)


def test_plan_from_recovery_plan_mapping():
    mgr = fresh_manager()
    plan = mgr.plan(
        {
            "workflow_id": "wf_test",
            "execution_id": "ex_test",
            "plan_id": "rplan_1",
            "checkpoint_id": "ckpt_test",
            "resume_node_id": "n_2",
            "target_nodes": ["n_2"],
            "reason": "from_recovery",
        }
    )
    assert plan.recovery_plan_reference == "rplan_1"
    assert plan.checkpoint_reference == "ckpt_test"
    assert plan.target_node == "n_2"


def test_async_wrappers():
    import asyncio

    mgr = fresh_manager(checkpoint_port=FakeCheckpointPort())

    async def _run():
        plan = await mgr.aplan(make_failure())
        await mgr.avalidate(plan, known_nodes=["n_1", "n_2"])
        return await mgr.aexecute(plan)

    result = asyncio.run(_run())
    assert result.status == RollbackStatus.COMPLETED
