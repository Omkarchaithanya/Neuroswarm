"""G15: table-driven should_skip_spec cost model."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import pytest

from neuroswarm_arm.runtime.armcascade.policies.cost_model import (
    CostSignals,
    should_skip_spec,
)
from neuroswarm_arm.runtime.dipa.interfaces.types import WorkloadClass


@dataclass
class _FakePlan:
    speculation: bool = True
    self_speculation: bool = False
    workload: Any = WorkloadClass.CODING
    metadata: dict | None = None
    max_tokens: int = 64


@pytest.fixture(autouse=True)
def _clear_skip_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "NSA_ASCR_SKIP_HISTORICAL_MIN",
        "NSA_ASCR_SKIP_PRESSURE_MAX",
        "NSA_ASCR_SKIP_MAX_TOKENS_MIN",
        "NSA_ASCR_COST_MODEL_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize(
    "hist,pressure,max_tokens,workload,expect_skip,reason",
    [
        # historical_acceptance=0.1, latency_pressure=0.1 → True (hist)
        (0.1, 0.1, 64, WorkloadClass.CODING, True, "hist"),
        # historical_acceptance=0.5, latency_pressure=0.1 → False
        (0.5, 0.1, 64, WorkloadClass.CODING, False, ""),
        # historical_acceptance=0.5, latency_pressure=0.9 → True (pressure)
        (0.5, 0.9, 64, WorkloadClass.CODING, True, "pressure"),
        # historical_acceptance=0.5, latency_pressure=0.1, max_tokens=4 → True
        (0.5, 0.1, 4, WorkloadClass.CODING, True, "short"),
        # workload=VISION → True
        (0.5, 0.1, 64, WorkloadClass.VISION, True, "vision"),
    ],
)
def test_should_skip_spec_table(
    hist: float,
    pressure: float,
    max_tokens: int,
    workload: WorkloadClass,
    expect_skip: bool,
    reason: str,
) -> None:
    budget = 1000.0
    signals = CostSignals(
        historical_acceptance=hist,
        latency_used_ms=pressure * budget,
        latency_budget_ms=budget,
        max_tokens=max_tokens,
        workload=workload,
    )
    plan = _FakePlan(workload=workload, max_tokens=max_tokens)
    skip, got_reason = should_skip_spec(plan, signals)
    assert skip is expect_skip
    if expect_skip:
        assert got_reason == reason
    else:
        assert got_reason == ""


def test_policy_apply_skips_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from neuroswarm_arm.runtime.armcascade.policies.engine import (
        DefaultCascadePolicyEngine,
    )

    monkeypatch.setenv("NSA_ASCR_COST_MODEL_ENABLED", "1")
    engine = DefaultCascadePolicyEngine(
        {"strategies": {"cost_model": {"enabled": True}}}
    )
    plan = _FakePlan(speculation=True)
    signals = CostSignals(
        historical_acceptance=0.1,
        latency_used_ms=100.0,
        latency_budget_ms=1000.0,
        max_tokens=64,
        workload=WorkloadClass.CODING,
    )
    out = engine.apply(plan, signals)
    assert out.speculation is False
    assert (out.metadata or {}).get("ascr_skip_spec_reason") == "hist"
    assert engine._last_skip_reason == "hist"


def test_policy_apply_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from neuroswarm_arm.runtime.armcascade.policies.engine import (
        DefaultCascadePolicyEngine,
    )

    monkeypatch.setenv("NSA_ASCR_COST_MODEL_ENABLED", "0")
    engine = DefaultCascadePolicyEngine(
        {"strategies": {"cost_model": {"enabled": False}}}
    )
    plan = _FakePlan(speculation=True)
    signals = CostSignals(
        historical_acceptance=0.1,
        latency_used_ms=900.0,
        latency_budget_ms=1000.0,
        max_tokens=4,
        workload=WorkloadClass.VISION,
    )
    out = engine.apply(plan, signals)
    assert out.speculation is True
    assert engine._last_skip_reason == ""
