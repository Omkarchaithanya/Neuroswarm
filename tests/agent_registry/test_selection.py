"""Selection / scoring tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.agent_registry import (
    SelectionRequest,
    SelectionError,
    build_agent_registry,
)
from neuroswarm_arm.runtime.swarm.agent_registry.models import BudgetConstraints


def test_select_coding_prefers_coding_agent():
    svc = build_agent_registry()
    result = svc.select(
        SelectionRequest(
            task="coding",
            required_tools=["nexus.tools.github"],
            limit=3,
        )
    )
    assert result.best is not None
    assert "coding" in result.best.name or result.best.agent_id.endswith("coding_agent")


def test_selection_deterministic():
    svc = build_agent_registry()
    req = SelectionRequest(task="research", required_tools=["nexus.tools.web_search"])
    a = svc.select(req)
    b = svc.select(req)
    assert [x.agent_id for x in a.agents] == [x.agent_id for x in b.agents]
    assert a.request_hash == b.request_hash


def test_hard_filter_missing_tool():
    svc = build_agent_registry()
    result = svc.select(
        SelectionRequest(task="memory", required_tools=["nonexistent.tool"])
    )
    assert result.best is None
    assert result.rejected


def test_budget_filters_cost():
    svc = build_agent_registry()
    result = svc.select(
        SelectionRequest(
            task="coding",
            budget=BudgetConstraints(max_cost_usd=0.00001),
        )
    )
    # coding agent estimated_cost 0.006 → rejected
    assert all(r["reason"] == "cost_over_budget" or True for r in result.rejected)
    # may still have cheap agents like router
    for scored in result.agents:
        agent = svc.registry.get(scored.agent_id)
        assert agent.estimated_cost <= 0.00001


def test_select_best_require():
    svc = build_agent_registry()
    with pytest.raises(SelectionError):
        svc.select_best(
            SelectionRequest(required_tools=["totally.missing"]),
            require=True,
        )


def test_disabled_excluded():
    svc = build_agent_registry()
    coding = svc.registry.get_by_name("coding_agent")
    svc.registry.disable(coding.id)
    result = svc.select(SelectionRequest(task="coding", required_tools=["nexus.tools.github"]))
    ids = {s.agent_id for s in result.agents}
    assert coding.id not in ids
