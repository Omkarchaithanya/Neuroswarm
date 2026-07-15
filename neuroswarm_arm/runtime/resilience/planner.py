"""Build AlternativeExecutionPlan from scored winner (not ARMORA planning)."""

from __future__ import annotations

from ._utils import new_id
from .execution import AlternativeExecutionPlan, ExecutionSnapshot
from .models import DecisionKind, ScoredCandidate


class ResiliencePlanner:
    """Map winning ScoredCandidate → AlternativeExecutionPlan."""

    def to_alternative_plan(
        self,
        scored: ScoredCandidate,
        plan: ExecutionSnapshot,
        *,
        reason: str = "",
        remaining_fallbacks: list[str] | None = None,
    ) -> AlternativeExecutionPlan:
        cand = scored.candidate
        return AlternativeExecutionPlan(
            plan_id=new_id("alt_"),
            execution_id=plan.execution_id,
            model=cand.model_id,
            backend=cand.backend,
            quant=cand.quant,
            context_length=cand.context_length,
            thread_count=cand.thread_count,
            reasoning_budget=cand.reasoning_budget,
            tools_enabled=cand.tools_enabled,
            cascade_strategy=cand.cascade_strategy,
            previous_model=plan.model,
            previous_backend=plan.backend,
            previous_quant=plan.quant,
            quality_delta=cand.quality_delta,
            latency_delta=cand.latency_delta,
            cost_delta=cand.cost_delta,
            budget_delta=cand.cost_delta,
            reason=reason or cand.reason,
            dimensions_changed=list(cand.dimensions_changed),
            decision=DecisionKind.TRANSITION,
            score=scored.score,
            score_factors=dict(scored.factors),
            fallbacks=list(remaining_fallbacks or plan.fallbacks),
            metadata={"candidate_id": cand.candidate_id},
        )
