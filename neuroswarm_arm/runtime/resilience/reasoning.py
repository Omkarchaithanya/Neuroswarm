"""Reasoning-budget fallback dimension helpers."""

from __future__ import annotations

from .models import FallbackCandidate, FallbackDimension


def suggest_reasoning_budget(
    current: int,
    needed: int,
    preferences: list[str] | None = None,
) -> int:
    """Reduce reasoning budget under pressure while meeting minimum need."""
    floor = max(0, needed)
    if preferences:
        prefs = sorted(
            (int(p) for p in preferences if str(p).lstrip("-").isdigit()),
            reverse=True,
        )
        for p in prefs:
            if p >= floor:
                return p
    if current >= floor:
        # Step down toward need when over-provisioned
        return max(floor, min(current, max(floor, current // 2 if current > floor * 2 else current)))
    return floor


def with_reasoning(candidate: FallbackCandidate, reasoning_budget: int) -> FallbackCandidate:
    dims = list(candidate.dimensions_changed)
    if FallbackDimension.REASONING_BUDGET not in dims:
        dims.append(FallbackDimension.REASONING_BUDGET)
    delta = float(reasoning_budget - candidate.reasoning_budget) * 0.0001
    return candidate.model_copy(
        update={
            "reasoning_budget": reasoning_budget,
            "dimensions_changed": dims,
            "cost_delta": candidate.cost_delta + delta,
            "reason": f"{candidate.reason};reasoning={reasoning_budget}".strip(";"),
        }
    )
