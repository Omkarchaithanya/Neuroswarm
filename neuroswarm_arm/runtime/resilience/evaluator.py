"""Continuous evaluation — should execution continue or transition."""

from __future__ import annotations

from .execution import ExecutionSnapshot
from .models import DecisionKind, HealthReport, RuntimeSignals
from .policy import ResiliencePolicy


class ResilienceEvaluator:
    """Decide CONTINUE vs TRANSITION vs DEGRADE_NOTIFY from health + policy."""

    def should_transition(
        self,
        plan: ExecutionSnapshot,
        signals: RuntimeSignals,
        health: HealthReport,
        policy: ResiliencePolicy | None,
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        threshold = policy.min_health_score if policy else 0.55
        fail_thresh = policy.failure_threshold if policy else 2

        if not signals.model_available:
            reasons.append("model_unavailable")
        if not signals.backend_available:
            reasons.append("backend_unavailable")
        if health.health_score < threshold:
            reasons.append("health_below_threshold")
        if signals.historical_failures >= fail_thresh:
            reasons.append("failure_threshold")
        if signals.budget_remaining_ratio <= 0.0:
            reasons.append("budget_exhausted")
        if signals.memory_pressure >= 0.95:
            reasons.append("critical_memory")
        if (
            policy is not None
            and signals.latency_p99_ms > policy.max_latency_ms
            and signals.historical_failures > 0
        ):
            reasons.append("latency_and_failures")

        # Context plan mismatch
        if signals.context_tokens_needed > plan.context_length:
            reasons.append("context_overflow")

        return (len(reasons) > 0, reasons)

    def decide_kind(
        self,
        *,
        should_transition: bool,
        has_alternative: bool,
        reasons: list[str],
    ) -> DecisionKind:
        if not should_transition:
            return DecisionKind.CONTINUE
        if has_alternative:
            return DecisionKind.TRANSITION
        return DecisionKind.DEGRADE_NOTIFY

    def should_continue(
        self,
        plan: ExecutionSnapshot,
        signals: RuntimeSignals,
        health: HealthReport,
        policy: ResiliencePolicy | None,
    ) -> bool:
        transition, _ = self.should_transition(plan, signals, health, policy)
        return not transition
