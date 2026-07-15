"""History + analytics tests."""

from __future__ import annotations

from .conftest import FakeCheckpointPort, fresh_manager, make_failure


def test_history_after_execute():
    mgr = fresh_manager(checkpoint_port=FakeCheckpointPort())
    plan = mgr.plan(make_failure())
    mgr.execute(plan)
    hist = mgr.history("ex_test")
    assert hist.depth == 1
    assert hist.entries[0].success
    assert hist.entries[0].strategy.value == plan.strategy.value


def test_analytics():
    mgr = fresh_manager(checkpoint_port=FakeCheckpointPort())
    for _ in range(2):
        plan = mgr.plan(make_failure())
        mgr.execute(plan)
    analytics = mgr.analytics(execution_id="ex_test")
    assert analytics.total_rollbacks == 2
    assert analytics.success_count == 2
    assert analytics.mean_duration_ms >= 0.0


def test_cancel_records_history():
    mgr = fresh_manager(checkpoint_port=FakeCheckpointPort())
    plan = mgr.plan(make_failure())
    from neuroswarm_arm.runtime.swarm.rollback import RollbackBuilder

    op = (
        RollbackBuilder()
        .rollback_id(plan.rollback_id)
        .workflow(plan.workflow_id, execution_id=plan.execution_id)
        .checkpoint(plan.checkpoint_reference)
        .strategy(plan.strategy)
        .reason(plan.reason)
        .build()
    )
    mgr.register(op)
    mgr.cancel(op.rollback_id)
    entry = mgr.history_store.get(op.rollback_id)
    assert entry is not None
    assert entry.status.value == "cancelled"
