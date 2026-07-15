"""Health evaluation tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.resilience import HealthEngine, HealthState

from .conftest import make_catalog, make_plan, make_signals


def test_healthy_signals_score_high():
    engine = HealthEngine()
    report = engine.evaluate(make_plan(), make_signals(), catalog=make_catalog())
    assert report.health_score >= 0.7
    assert report.state == HealthState.HEALTHY


def test_model_unavailable_lowers_score():
    engine = HealthEngine()
    report = engine.evaluate(
        make_plan(),
        make_signals(model_available=False),
        catalog=make_catalog(),
    )
    assert report.health_score < 0.5
    assert "model_unavailable" in report.reasons
    assert report.state == HealthState.UNAVAILABLE


def test_memory_pressure_flagged():
    engine = HealthEngine()
    report = engine.evaluate(
        make_plan(),
        make_signals(memory_pressure=0.95),
        catalog=make_catalog(),
    )
    assert "memory_pressure" in report.reasons
    assert report.factors["memory"] < 0.2


def test_latency_slo_breach():
    engine = HealthEngine()
    report = engine.evaluate(
        make_plan(),
        make_signals(latency_p99_ms=9000.0, latency_slo_ms=4000.0),
        catalog=make_catalog(),
    )
    assert "latency_slo_breach" in report.reasons


def test_budget_exhausted():
    engine = HealthEngine()
    report = engine.evaluate(
        make_plan(),
        make_signals(budget_remaining_usd=0.0, budget_remaining_ratio=0.0),
        catalog=make_catalog(),
    )
    assert "budget_exhausted" in report.reasons


def test_context_incompatible():
    engine = HealthEngine()
    report = engine.evaluate(
        make_plan(model="TinyLlama", context_length=2048),
        make_signals(context_tokens_needed=10000),
        catalog=make_catalog(),
    )
    assert "context_incompatible" in report.reasons or "context_plan_too_small" in report.reasons
