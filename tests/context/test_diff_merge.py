"""Diff + merge tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.context import (
    ConflictPolicy,
    MergeConflictError,
    SwarmContextBuilder,
    child_context,
    diff_contexts,
    merge_budget,
    merge_contexts,
)
from neuroswarm_arm.runtime.swarm.context.budget import BudgetContext


def test_diff_detects_budget_change():
    a = SwarmContextBuilder().request(prompt="d").budget(cost_usd_used=0.0).build()
    b = a.evolve(budget=a.budget.apply_usage(cost_usd=0.5))
    d = diff_contexts(a, b)
    assert d.identical is False
    assert any(f.path == "budget.cost_usd_used" for f in d.budget)


def test_merge_fan_in():
    parent = (
        SwarmContextBuilder()
        .request(prompt="m")
        .budget(cost_usd_limit=5.0, cost_usd_used=1.0)
        .execution(run_id="p", pending_nodes=["a", "b"])
        .build()
    )
    c1 = child_context(parent, node_id="a")
    c1 = c1.evolve(
        execution=c1.execution.mark_completed("a", result={"ok": 1}),
        budget=c1.budget.apply_usage(cost_usd=0.2),
        memory=c1.memory.model_copy(update={"scratchpad": {"x": 1}}),
    )
    c2 = child_context(parent, node_id="b")
    c2 = c2.evolve(
        execution=c2.execution.mark_completed("b", result={"ok": 2}),
        budget=c2.budget.apply_usage(cost_usd=0.3),
        memory=c2.memory.model_copy(update={"scratchpad": {"y": 2}}),
    )
    merged = merge_contexts(c1, c2, budget_policy=ConflictPolicy.SUM_USAGE)
    assert "a" in merged.execution.completed_nodes
    assert "b" in merged.execution.completed_nodes
    # children each started with parent used=1.0 then +0.2 / +0.3 → merge sums = 1.2+1.3=2.5
    assert merged.budget.cost_usd_used == pytest.approx(2.5)
    assert merged.memory.scratchpad["x"] == 1
    assert merged.memory.scratchpad["y"] == 2
    assert merged.metrics.merge_count >= 1


def test_merge_budget_raise_on_envelope_conflict():
    a = BudgetContext(envelope_id="e1", frozen=True)
    b = BudgetContext(envelope_id="e2", frozen=True)
    with pytest.raises(MergeConflictError):
        merge_budget(a, b, policy=ConflictPolicy.RAISE)
