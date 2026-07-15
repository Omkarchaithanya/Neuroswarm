"""Validation + budget + execution unit tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.context import (
    BudgetError,
    SwarmContext,
    SwarmContextBuilder,
    ValidationError,
    assert_valid,
    validate_context,
)
from neuroswarm_arm.runtime.swarm.context.budget import BudgetContext
from neuroswarm_arm.runtime.swarm.context.validators import assert_budget


def test_validate_missing_request():
    ctx = SwarmContext()
    report = validate_context(ctx, require_request=True, require_execution=False)
    assert not report.ok
    assert any("missing request" in e for e in report.errors)


def test_assert_valid_ok():
    ctx = SwarmContextBuilder().request(prompt="ok").execution(run_id="r").build(
        require_request=True, require_execution=True
    )
    assert_valid(ctx, require_request=True, require_execution=True)


def test_assert_valid_raises():
    with pytest.raises(ValidationError):
        assert_valid(SwarmContext(), require_request=True)


def test_budget_remaining_and_apply():
    b = BudgetContext(cost_usd_limit=1.0, tokens_limit=100.0)
    assert b.remaining_cost() == 1.0
    b2 = b.apply_usage(cost_usd=0.25, tokens=10)
    assert b2.cost_usd_used == 0.25
    assert b2.remaining_cost() == pytest.approx(0.75)
    assert b2.remaining_tokens() == pytest.approx(90)
    with pytest.raises(BudgetError):
        b.apply_usage(cost_usd=-1)


def test_budget_exhausted():
    b = BudgetContext(cost_usd_limit=1.0, cost_usd_used=1.0)
    assert b.is_exhausted()


def test_assert_budget():
    assert_budget(BudgetContext(cost_usd_limit=1.0))


def test_execution_mark_completed_failed():
    ctx = SwarmContextBuilder().request(prompt="e").execution(run_id="r", pending_nodes=["n1"]).build()
    ex = ctx.execution.mark_completed("n1", result={"v": 1})
    assert "n1" in ex.completed_nodes
    assert ex.node_results["n1"]["v"] == 1
    ex2 = ex.mark_failed("n2", "boom", attempt=1)
    assert "n2" in ex2.failed_nodes
    assert ex2.retries["n2"] == 1
