"""Deterministic candidate scoring — no ML."""

from __future__ import annotations

from ._utils import clamp01
from .execution import ExecutionSnapshot
from .models import (
    FallbackCandidate,
    ModelProfile,
    RuntimeSignals,
    ScoreWeights,
    ScoredCandidate,
)
from .policy import ResiliencePolicy


class DeterministicScorer:
    """Weighted multi-factor scorer with stable tie-break."""

    def rank(
        self,
        candidates: list[FallbackCandidate],
        *,
        plan: ExecutionSnapshot,
        signals: RuntimeSignals,
        policy: ResiliencePolicy,
        catalog: dict[str, ModelProfile],
        health_score: float,
    ) -> list[ScoredCandidate]:
        weights = policy.score_weights
        scored: list[ScoredCandidate] = []
        for cand in candidates:
            factors = self._factors(
                cand,
                plan=plan,
                signals=signals,
                policy=policy,
                catalog=catalog,
                health_score=health_score,
            )
            total = self._weighted(factors, weights)
            scored.append(ScoredCandidate(candidate=cand, score=total, factors=factors))

        scored.sort(
            key=lambda s: (
                -s.score,
                s.candidate.model_id,
                s.candidate.backend,
                s.candidate.quant,
            )
        )
        return scored

    def _factors(
        self,
        cand: FallbackCandidate,
        *,
        plan: ExecutionSnapshot,
        signals: RuntimeSignals,
        policy: ResiliencePolicy,
        catalog: dict[str, ModelProfile],
        health_score: float,
    ) -> dict[str, float]:
        profile = catalog.get(cand.model_id)
        quality = clamp01(1.0 + cand.quality_delta)
        if profile is not None:
            quality = clamp01(quality * (0.5 + 0.5 * min(profile.priority, 2.0) / 2.0))

        latency_est = profile.estimated_latency if profile else 100.0
        latency = clamp01(1.0 - (latency_est / max(signals.latency_slo_ms, 1.0)))

        cost_est = profile.estimated_cost if profile else 0.001
        max_cost = policy.max_budget_usd or signals.max_cost_usd or 0.05
        cost = clamp01(1.0 - (cost_est / max(max_cost, 1e-9)))

        mem_est = profile.estimated_memory if profile else 4.0
        memory = clamp01(
            1.0 - (mem_est / max(signals.max_memory_gb, policy.max_memory_gb, 1.0))
        )

        policy_priority = 0.5
        prefs = list(policy.preferred_models)
        if cand.model_id in prefs:
            idx = prefs.index(cand.model_id)
            policy_priority = clamp01(1.0 - (idx / max(len(prefs), 1)))
        elif cand.model_id == plan.model:
            policy_priority = 0.9

        avail = profile.availability if profile else 0.5
        model_h = signals.model_health.get(cand.model_id, avail)
        if not signals.model_available and cand.model_id == plan.model:
            model_h = 0.0
            avail = 0.0
        backend_h = signals.backend_health.get(cand.backend, 1.0)
        if not signals.backend_available and cand.backend == plan.backend:
            backend_h = 0.0
        elif cand.backend not in signals.backend_health and not signals.backend_available:
            # Unknown backends stay usable when only current backend is down
            backend_h = 1.0 if cand.backend != plan.backend else 0.0
        health = clamp01(0.5 * health_score + 0.25 * model_h + 0.25 * backend_h)

        backend_compat = 1.0
        if profile is not None:
            backend_compat = 1.0 if cand.backend in profile.supported_backends else 0.0

        budget_fit = clamp01(signals.budget_remaining_ratio)
        if (
            signals.budget_remaining_usd is not None
            and cost_est > signals.budget_remaining_usd
        ):
            budget_fit = 0.0

        context_compat = 1.0
        if profile is not None:
            if signals.context_tokens_needed > cand.context_length:
                context_compat = 0.0
            elif signals.context_tokens_needed > profile.context_length:
                context_compat = 0.0

        return {
            "quality": quality,
            "latency": latency,
            "cost": cost,
            "memory": memory,
            "policy_priority": policy_priority,
            "health": health,
            "availability": clamp01(avail),
            "backend_compat": backend_compat,
            "budget_fit": budget_fit,
            "context_compat": context_compat,
        }

    def _weighted(self, factors: dict[str, float], weights: ScoreWeights) -> float:
        raw = {
            "quality": weights.quality,
            "latency": weights.latency,
            "cost": weights.cost,
            "memory": weights.memory,
            "policy_priority": weights.policy_priority,
            "health": weights.health,
            "availability": weights.availability,
            "backend_compat": weights.backend_compat,
            "budget_fit": weights.budget_fit,
            "context_compat": weights.context_compat,
        }
        total_w = sum(raw.values()) or 1.0
        return sum(factors[k] * (raw[k] / total_w) for k in raw)
