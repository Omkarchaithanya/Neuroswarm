"""Policy evaluation tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.rollback import (
    PolicyEngine,
    PolicyError,
    RollbackObservation,
    always_rollback,
    automatic_rollback,
    budget_rollback,
    custom_rollback,
    failure_rollback,
    latency_rollback,
    manual_rollback,
    threshold_rollback,
)


def test_always_and_manual():
    engine = PolicyEngine([always_rollback(), manual_rollback()])
    assert engine.should_rollback(
        RollbackObservation(workflow_id="w", execution_id="e")
    )
    engine2 = PolicyEngine([manual_rollback()])
    assert not engine2.should_rollback(
        RollbackObservation(workflow_id="w", execution_id="e")
    )
    assert engine2.should_rollback(
        RollbackObservation(workflow_id="w", execution_id="e", manual=True)
    )


def test_automatic_failure():
    engine = PolicyEngine([automatic_rollback()])
    assert engine.should_rollback(
        RollbackObservation(
            workflow_id="w", execution_id="e", event_kind="failure"
        )
    )


def test_threshold_budget_latency_failure():
    obs = RollbackObservation(
        workflow_id="w",
        execution_id="e",
        failure_count=3,
        latency_ms=500,
        budget_remaining=0.1,
        threshold=2.0,
    )
    assert PolicyEngine([threshold_rollback(2.0)]).should_rollback(obs)
    assert PolicyEngine([budget_rollback(0.5)]).should_rollback(obs)
    assert PolicyEngine([latency_rollback(100)]).should_rollback(obs)
    assert PolicyEngine([failure_rollback(2)]).should_rollback(obs)


def test_custom_predicate():
    engine = PolicyEngine(
        [custom_rollback("p1")],
        custom_predicates={"p1": lambda o: o.failure_count > 0},
    )
    assert engine.should_rollback(
        RollbackObservation(workflow_id="w", execution_id="e", failure_count=1)
    )


def test_custom_without_predicate_errors():
    engine = PolicyEngine([custom_rollback("missing")])
    with pytest.raises(PolicyError):
        engine.should_rollback(
            RollbackObservation(workflow_id="w", execution_id="e")
        )
