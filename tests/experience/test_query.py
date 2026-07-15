from __future__ import annotations

from datetime import datetime, timedelta, timezone

from neuroswarm_arm.runtime.swarm.experience import ExperienceFilter, with_predicate

from .conftest import fresh_store, make_record


def test_query_by_dimensions():
    store = fresh_store()
    store.record(
        make_record(
            execution_id="q1",
            workflow_id="wf_a",
            models_used=["m1"],
            backends_used=["b1"],
            tags=["t1"],
            latency=50,
            estimated_cost=0.01,
            success=True,
        )
    )
    store.record(
        make_record(
            execution_id="q2",
            workflow_id="wf_b",
            models_used=["m2"],
            backends_used=["b2"],
            tags=["t2"],
            latency=500,
            estimated_cost=0.5,
            success=False,
            failure_reason="boom",
        )
    )

    assert len(store.query.by_workflow("wf_a")) == 1
    assert len(store.query.by_model("m1")) == 1
    assert len(store.query.by_backend("b2")) == 1
    assert len(store.query.by_agent("agt_coder")) == 2
    assert len(store.query.by_success(False)) == 1

    filt = ExperienceFilter(max_latency=100, min_quality=0.5, tag="t1")
    assert len(store.filter(filt)) == 1

    filt2 = ExperienceFilter(min_cost=0.1, success=False)
    assert store.filter(filt2)[0].execution_id == "q2"


def test_custom_predicate():
    store = fresh_store()
    store.record(make_record(execution_id="p1", retry_count=0))
    store.record(make_record(execution_id="p2", retry_count=3))
    filt = with_predicate(lambda r: r.retry_count >= 2)
    assert [r.execution_id for r in store.filter(filt)] == ["p2"]


def test_date_and_budget_filter():
    store = fresh_store()
    now = datetime.now(timezone.utc)
    store.record(
        make_record(
            execution_id="d1",
            timestamp=now - timedelta(days=2),
        )
    )
    store.record(make_record(execution_id="d2", timestamp=now))
    filt = ExperienceFilter(since=now - timedelta(days=1), budget_envelope_id="env_1")
    ids = {r.execution_id for r in store.filter(filt)}
    assert ids == {"d2"}
