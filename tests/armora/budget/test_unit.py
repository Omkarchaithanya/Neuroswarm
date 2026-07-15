"""Unit tests — BudgetEnvelope core."""

from __future__ import annotations

from pathlib import Path

import pytest

from neuroswarm_arm.armora.budget import (
    BudgetValidator,
    Hardness,
    PlanAction,
    ViolationState,
    build_budget_service,
    load_budget_config,
)


@pytest.fixture
def svc(request):
    root = Path("work") / "test_budget" / request.node.name
    root.mkdir(parents=True, exist_ok=True)
    cfg = load_budget_config(work_dir=root)
    cfg.persistence = "sqlite"
    return build_budget_service(cfg)


def test_create_freeze_immutable(svc):
    env, state, decision = svc.create_and_freeze_sync(
        request_id="r1", agent_role="chat", tenant_id="t1"
    )
    assert decision.accepted
    assert env.frozen
    assert str(env.envelope_id) == state.envelope_id
    assert "cost_usd" in env.categories
    assert state.remaining("cost_usd") == pytest.approx(env.categories["cost_usd"].limit)


def test_research_policy_higher_budget(svc):
    chat, _, _ = svc.create_and_freeze_sync(request_id="c1", agent_role="chat")
    research, _, _ = svc.create_and_freeze_sync(request_id="r1", agent_role="research")
    assert research.categories["cost_usd"].limit > chat.categories["cost_usd"].limit
    assert research.categories["reasoning_tokens"].limit > chat.categories["reasoning_tokens"].limit


def test_validator_hard_failure():
    from neuroswarm_arm.armora.budget.categories import build_category
    from neuroswarm_arm.armora.budget.envelope import BudgetEnvelope

    env = BudgetEnvelope(
        categories={
            "cost_usd": build_category("cost_usd", limit=0.01, hardness=Hardness.HARD),
        }
    )
    decision = BudgetValidator().validate_envelope(env, projected={"cost_usd": 1.0})
    assert not decision.accepted
    assert decision.hard_failures


def test_reserve_reconcile_accounting(svc):
    env, state, _ = svc.create_and_freeze_sync(request_id="r2", agent_role="chat")
    eid = str(env.envelope_id)
    assert svc.tracker.reserve(eid, {"cost_usd": 0.001, "completion_tokens": 10})
    svc.tracker.reconcile(
        eid,
        {"cost_usd": 0.0008, "completion_tokens": 8},
        reserved={"cost_usd": 0.001, "completion_tokens": 10},
    )
    st = svc.tracker.get_state(eid)
    assert st.categories["cost_usd"].consumed == pytest.approx(0.0008)
    assert st.accounting.completion_tokens == 8
    assert not svc.tracker.hard_breached(eid)


def test_violation_on_overconsume(svc):
    env, _, _ = svc.create_and_freeze_sync(
        request_id="r3",
        agent_role="chat",
        overrides={"cost_usd": 0.001},
    )
    eid = str(env.envelope_id)
    ok = svc.tracker.consume(eid, {"cost_usd": 0.002})
    assert ok is False


def test_can_afford_tier(svc):
    env, _, _ = svc.create_and_freeze_sync(request_id="r4", agent_role="chat")
    d = svc.can_afford(str(env.envelope_id), PlanAction.tier(1))
    assert d.affordable
    d3 = svc.can_afford(str(env.envelope_id), PlanAction.frontier_model())
    assert isinstance(d3.affordable, bool)


def test_optimizer_degrade(svc):
    env, state, _ = svc.create_and_freeze_sync(
        request_id="r5",
        agent_role="chat",
        overrides={"cost_usd": 0.0001, "reasoning_tokens": 10},
    )
    result = svc.optimizer.optimize(
        env,
        state,
        projected={"cost_usd": 1.0, "reasoning_tokens": 5000},
        plan={"tier": 3, "reasoning_tokens": 5000, "prompt_tokens": 1000},
    )
    assert result.actions_taken
    assert (
        "cut_reasoning" in result.actions_taken
        or "abort" in result.actions_taken
        or result.decision.optimized
    )


def test_finalize_reports_persist(svc):
    env, _, _ = svc.create_and_freeze_sync(request_id="r6", agent_role="summarization")
    eid = str(env.envelope_id)
    svc.tracker.consume(eid, {"cost_usd": 0.0001, "completion_tokens": 5})
    import asyncio

    bundle = asyncio.run(svc.finalize(eid))
    assert bundle.budget.envelope_id == eid
    assert bundle.cost.estimated_cost_usd >= 0
    hist = svc.persistence.query_history(limit=10)
    assert any(str(h.get("envelope_id")) == eid or h.get("request_id") == "r6" for h in hist)


def test_category_remaining():
    from neuroswarm_arm.armora.budget.categories import CostBudget

    c = CostBudget(limit=1.0, consumed=0.3, reserved=0.2)
    assert c.remaining == pytest.approx(0.5)
    c.apply_consume(0.6)
    assert c.violation in {ViolationState.WARNING, ViolationState.BREACHED, ViolationState.NONE}
