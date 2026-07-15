from __future__ import annotations

import time

from .conftest import fresh_store, make_record


def test_append_and_query_perf():
    store = fresh_store()
    n = 500
    t0 = time.perf_counter()
    for i in range(n):
        store.record(
            make_record(
                execution_id=f"perf_{i}",
                workflow_id=f"wf_{i % 10}",
                latency=float(i % 100),
            )
        )
    elapsed_write = time.perf_counter() - t0
    t1 = time.perf_counter()
    hits = store.query.by_workflow("wf_1")
    elapsed_query = time.perf_counter() - t1
    assert len(hits) == 50
    # generous CI threshold
    assert elapsed_write < 15.0, f"write too slow: {elapsed_write:.3f}s"
    assert elapsed_query < 1.0, f"query too slow: {elapsed_query:.3f}s"
