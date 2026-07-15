"""Performance smoke — deterministic ranking stays fast."""

from __future__ import annotations

import time

from .conftest import fresh_engine, make_plan, make_signals


def test_evaluate_latency_smoke():
    engine = fresh_engine()
    plan = make_plan()
    signals = make_signals(model_available=False, historical_failures=2)
    # warm
    engine.evaluate(plan, signals)
    t0 = time.perf_counter()
    for _ in range(50):
        engine.evaluate(plan, signals)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    # Generous bound for CI / Windows — decision path is CPU-only
    assert elapsed_ms < 5000.0


def test_rank_stable_under_repeat():
    engine = fresh_engine()
    signals = make_signals(model_available=False, historical_failures=2)
    results = [
        engine.evaluate(make_plan(), signals).alternative.model
        for _ in range(10)
    ]
    assert len(set(results)) == 1
