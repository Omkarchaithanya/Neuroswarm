"""Lightweight performance smoke tests."""

from __future__ import annotations

import time

from .conftest import fresh_manager, make_checkpoint


def test_bulk_create_throughput() -> None:
    mgr = fresh_manager()
    n = 200
    t0 = time.perf_counter()
    for _ in range(n):
        mgr.checkpoint(make_checkpoint())
    elapsed = time.perf_counter() - t0
    # Soft bound — in-memory append should be well under 5s for 200
    assert elapsed < 5.0
    assert mgr.metrics.checkpoint_count == n


def test_restore_latency_recorded() -> None:
    mgr = fresh_manager()
    cid = mgr.create(
        {
            "workflow_id": "wf_p",
            "execution_id": "ex_p",
            "completed_nodes": ["n_1"],
        }
    )
    mgr.restore(cid)
    assert mgr.metrics.restores_total == 1
    assert mgr.metrics.recovery_latency_ms_total >= 0.0
