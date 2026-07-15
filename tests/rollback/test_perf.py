"""Performance smoke tests for Rollback Manager."""

from __future__ import annotations

import time

from .conftest import FakeCheckpointPort, fresh_manager, make_failure


def test_plan_validate_execute_perf_budget():
    mgr = fresh_manager(checkpoint_port=FakeCheckpointPort())
    started = time.perf_counter()
    n = 50
    for i in range(n):
        plan = mgr.plan(
            make_failure(
                reason=f"fail_{i}",
            )
        )
        mgr.validate(plan, known_nodes=["n_1", "n_2"])
        mgr.execute(plan)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    # Generous smoke budget — consistency restore descriptors only
    assert elapsed_ms < 5000.0
    snap = mgr.metrics.snapshot()
    assert snap["success_count"] == n
    assert snap["rollback_count"] >= n
