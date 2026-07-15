"""Deterministic selection tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.sub_swarms import (
    BudgetConstraints,
    LifecycleState,
    SwarmSelectionRequest,
    SwarmSelector,
)


def test_select_coding_builtin(manager):
    result = manager.select(
        SwarmSelectionRequest(workflow_type="coding", limit=3)
    )
    assert result.templates
    assert result.templates[0].template_id == "nexus.swarms.coding"
    # deterministic
    result2 = manager.select(
        SwarmSelectionRequest(workflow_type="coding", limit=3)
    )
    assert [t.template_id for t in result.templates] == [
        t.template_id for t in result2.templates
    ]
    assert result.request_hash == result2.request_hash


def test_hard_filter_budget(manager):
    result = manager.select(
        SwarmSelectionRequest(
            workflow_type="benchmark",
            budget=BudgetConstraints(max_cost_usd=0.001),
            limit=5,
        )
    )
    assert result.templates == []
    assert result.rejected


def test_non_ready_rejected(empty_registry, sample_template):
    empty_registry.register(sample_template, promote_to=LifecycleState.REGISTERED)
    selector = SwarmSelector()
    result = selector.select(
        empty_registry.as_list(),
        SwarmSelectionRequest(workflow_type="testing"),
    )
    assert not result.templates
    assert any(r["reason"].startswith("status=") for r in result.rejected)


def test_select_best(manager):
    best = manager.select_best(
        SwarmSelectionRequest(workflow_type="planning", limit=1)
    )
    assert best is not None
    assert best.template_id == "nexus.swarms.planning"


def test_preferred_boost(manager):
    result = manager.select(
        SwarmSelectionRequest(
            preferred_templates=["nexus.swarms.research"],
            limit=10,
        )
    )
    ids = [t.template_id for t in result.templates]
    assert "nexus.swarms.research" in ids
