from __future__ import annotations

from .conftest import fresh_store, make_record


def test_analytics_aggregates():
    store = fresh_store()
    store.record(
        make_record(
            execution_id="a1",
            latency=100,
            estimated_cost=0.1,
            success=True,
            retry_count=0,
            models_used=["m1"],
        )
    )
    store.record(
        make_record(
            execution_id="a2",
            latency=200,
            estimated_cost=0.3,
            success=False,
            failure_reason="x",
            retry_count=2,
            models_used=["m1", "m2"],
        )
    )
    report = store.compute_analytics()
    assert report.count == 2
    assert report.failure_rate == 0.5
    assert report.average_latency == 150.0
    assert report.average_cost == 0.2
    assert report.model_utilization["m1"] == 2
    assert report.retry_frequency == 0.5
    assert "agt_coder" in report.agent_utilization
    assert report.budget_efficiency >= 0.0
    assert store.metrics.analytics_runs == 1
