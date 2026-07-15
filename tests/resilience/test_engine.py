"""ResilienceEngine integration tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.resilience import DecisionKind, AlternativeExecutionPlan

from .conftest import fresh_engine, make_plan, make_signals


def test_evaluate_continue_when_healthy():
    engine = fresh_engine()
    decision = engine.evaluate(make_plan(), make_signals())
    assert decision.kind == DecisionKind.CONTINUE
    assert decision.alternative is None


def test_evaluate_transition_on_model_failure():
    engine = fresh_engine()
    decision = engine.evaluate(
        make_plan(),
        make_signals(model_available=False, historical_failures=2),
    )
    assert decision.kind == DecisionKind.TRANSITION
    assert isinstance(decision.alternative, AlternativeExecutionPlan)
    assert decision.alternative.model != "Qwen3-8B"
    assert decision.alternative.previous_model == "Qwen3-8B"


def test_propose_returns_plan_or_none():
    engine = fresh_engine()
    assert engine.propose(make_plan(), make_signals()) is None
    alt = engine.propose(
        make_plan(),
        make_signals(model_available=False, historical_failures=2),
    )
    assert alt is not None
    patch = alt.to_plan_patch()
    assert "model" in patch
    assert "backend" in patch
    assert "quant" in patch
    assert "rmre_plan_id" in patch["metadata"]


@pytest.mark.asyncio
async def test_aevaluate():
    engine = fresh_engine()
    decision = await engine.aevaluate(make_plan(), make_signals())
    assert decision.kind == DecisionKind.CONTINUE


def test_metrics_updated_on_fallback():
    engine = fresh_engine()
    engine.evaluate(
        make_plan(),
        make_signals(model_available=False, historical_failures=2),
    )
    snap = engine.metrics.snapshot()
    assert snap["fallback_count"] >= 1
    assert snap["success_count"] >= 1


def test_events_emitted():
    engine = fresh_engine()
    engine.evaluate(
        make_plan(),
        make_signals(model_available=False, historical_failures=2),
    )
    types = [e.type for e in engine.events.history()]
    assert "FallbackTriggered" in types
    assert "RecoveryCompleted" in types
