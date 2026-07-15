"""Offline acceptance-rate simulation framework."""

from __future__ import annotations

from neuroswarm_arm.runtime.armcascade.acceptance.engine import AdaptiveAcceptanceEngine
from neuroswarm_arm.runtime.armcascade.interfaces.types import (
    AcceptanceAction,
    AcceptanceSignals,
    TaskKind,
)


def simulate_acceptance_curve(
    agreements: list[float],
    *,
    accept_threshold: float = 0.7,
    escalate_threshold: float = 0.4,
) -> dict[str, float]:
    eng = AdaptiveAcceptanceEngine()
    counts = {a.value: 0 for a in AcceptanceAction}
    for agr in agreements:
        d = eng.decide(
            AcceptanceSignals(
                confidence=0.0,
                agreement=agr,
                entropy=1.0 - agr,
                quality_score=agr,
                historical_acceptance=0.7,
                task_kind=TaskKind.CHAT,
                tool_confidence=0.0,
                reasoning_confidence=0.6,
                latency_budget_ms=4000,
                latency_used_ms=200,
                cpu_utilization=0.4,
                kv_pressure=0.1,
                cache_hit_ratio=0.2,
                draft_len=8,
                accepted_prefix_len=max(0, int(agr * 8)),
                accept_threshold=accept_threshold,
                escalate_threshold=escalate_threshold,
            )
        )
        counts[d.action.value] += 1
    n = max(1, len(agreements))
    return {k: v / n for k, v in counts.items()}


def test_simulation_high_agreement_accepts() -> None:
    rates = simulate_acceptance_curve([0.9, 0.85, 0.95, 0.8])
    assert rates.get("accept", 0) + rates.get("partial_accept", 0) > 0.5


def test_simulation_low_agreement_escalates() -> None:
    rates = simulate_acceptance_curve([0.05, 0.1, 0.0, 0.15])
    assert rates.get("escalate", 0) + rates.get("reject", 0) > 0.5
