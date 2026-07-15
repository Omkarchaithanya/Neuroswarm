"""Port contract tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.rollback import (
    IRollbackManagerPort,
    build_rollback_manager,
)

from .conftest import FakeCheckpointPort, make_failure


def test_isinstance_port():
    mgr = build_rollback_manager(checkpoint_port=FakeCheckpointPort())
    assert isinstance(mgr, IRollbackManagerPort)


def test_port_surface():
    mgr = build_rollback_manager(checkpoint_port=FakeCheckpointPort())
    plan = mgr.plan(make_failure())
    report = mgr.validate(plan, known_nodes=["n_1", "n_2", "n_3"])
    assert report.ok
    result = mgr.execute(plan)
    assert result.rollback_id == plan.rollback_id
