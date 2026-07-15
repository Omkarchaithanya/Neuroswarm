"""Constraint solver — hard-reject invalid candidates."""

from __future__ import annotations

from .backend import backend_compatible
from .exceptions import ConstraintViolation
from .execution import ExecutionSnapshot
from .models import FallbackCandidate, ModelProfile, RuntimeSignals
from .policy import ResiliencePolicy
from .quantization import quant_supported


class ConstraintSolver:
    """Validate candidates against budget / latency / memory / compat constraints."""

    def filter(
        self,
        candidates: list[FallbackCandidate],
        *,
        plan: ExecutionSnapshot,
        signals: RuntimeSignals,
        policy: ResiliencePolicy,
        catalog: dict[str, ModelProfile],
    ) -> list[FallbackCandidate]:
        return [
            c
            for c in candidates
            if self.validate(
                c,
                plan=plan,
                signals=signals,
                policy=policy,
                catalog=catalog,
                raise_on_fail=False,
            )
        ]

    def validate(
        self,
        candidate: FallbackCandidate,
        *,
        plan: ExecutionSnapshot,
        signals: RuntimeSignals,
        policy: ResiliencePolicy,
        catalog: dict[str, ModelProfile],
        raise_on_fail: bool = True,
    ) -> bool:
        try:
            self._check(candidate, plan, signals, policy, catalog)
            return True
        except ConstraintViolation:
            if raise_on_fail:
                raise
            return False

    def _check(
        self,
        candidate: FallbackCandidate,
        plan: ExecutionSnapshot,
        signals: RuntimeSignals,
        policy: ResiliencePolicy,
        catalog: dict[str, ModelProfile],
    ) -> None:
        profile = catalog.get(candidate.model_id)
        if profile is None:
            raise ConstraintViolation(
                f"unknown model: {candidate.model_id}", constraint="model"
            )

        if not backend_compatible(profile, candidate.backend):
            raise ConstraintViolation(
                f"backend {candidate.backend} unsupported by {candidate.model_id}",
                constraint="backend",
            )

        if not quant_supported(profile, candidate.quant):
            raise ConstraintViolation(
                f"quant {candidate.quant} unsupported by {candidate.model_id}",
                constraint="quantization",
            )

        needed = max(signals.context_tokens_needed, policy.min_context_length)
        if candidate.context_length < needed:
            raise ConstraintViolation(
                f"context {candidate.context_length} < needed {needed}",
                constraint="context",
            )
        if candidate.context_length > profile.context_length:
            raise ConstraintViolation(
                f"context {candidate.context_length} > model max {profile.context_length}",
                constraint="context",
            )

        max_mem = min(signals.max_memory_gb, policy.max_memory_gb)
        if profile.estimated_memory > max_mem:
            raise ConstraintViolation(
                f"memory {profile.estimated_memory} > max {max_mem}",
                constraint="memory",
            )

        if profile.estimated_latency > policy.max_latency_ms * 1.5:
            raise ConstraintViolation(
                f"latency estimate {profile.estimated_latency} exceeds policy",
                constraint="latency",
            )

        max_budget = policy.max_budget_usd
        if max_budget is None:
            max_budget = signals.max_cost_usd
        if max_budget is not None and profile.estimated_cost > max_budget:
            raise ConstraintViolation(
                f"cost {profile.estimated_cost} > budget {max_budget}",
                constraint="budget",
            )
        if (
            signals.budget_remaining_usd is not None
            and profile.estimated_cost > signals.budget_remaining_usd
        ):
            raise ConstraintViolation(
                "insufficient remaining budget",
                constraint="budget",
            )

        if signals.tools_required and not candidate.tools_enabled:
            raise ConstraintViolation(
                "tools required but candidate disables tools",
                constraint="tools",
            )

        if candidate.thread_count > signals.thread_available and signals.thread_available > 0:
            raise ConstraintViolation(
                f"threads {candidate.thread_count} > available {signals.thread_available}",
                constraint="threads",
            )

        _ = plan
