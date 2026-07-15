"""Evaluator tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.resilience import (
    DecisionKind,
    HealthEngine,
    ResilienceEvaluator,
    default_policy,
)

from .conftest import make_catalog, make_plan, make_signals


def test_healthy_should_continue():
    health = HealthEngine().evaluate(make_plan(), make_signals(), catalog=make_catalog())
    ev = ResilienceEvaluator()
    assert ev.should_continue(make_plan(), make_signals(), health, default_policy())


def test_failures_trigger_transition():
    signals = make_signals(historical_failures=3, model_available=False)
    health = HealthEngine().evaluate(make_plan(), signals, catalog=make_catalog())
    ev = ResilienceEvaluator()
    should, reasons = ev.should_transition(
        make_plan(), signals, health, default_policy()
    )
    assert should
    assert reasons


def test_decide_kind_degrade_when_no_alt():
    ev = ResilienceEvaluator()
    assert (
        ev.decide_kind(should_transition=True, has_alternative=False, reasons=["x"])
        == DecisionKind.DEGRADE_NOTIFY
    )
    assert (
        ev.decide_kind(should_transition=True, has_alternative=True, reasons=["x"])
        == DecisionKind.TRANSITION
    )
    assert (
        ev.decide_kind(should_transition=False, has_alternative=False, reasons=[])
        == DecisionKind.CONTINUE
    )
