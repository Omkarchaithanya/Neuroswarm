"""Health evaluation engine — no inference."""

from __future__ import annotations

from . import events as ev
from ._utils import clamp01
from .execution import ExecutionSnapshot
from .models import (
    ComponentHealth,
    HealthReport,
    HealthState,
    ModelProfile,
    RuntimeSignals,
)


class HealthEngine:
    """Evaluate model / backend / resource health into a HealthReport."""

    def __init__(self, *, events: ev.EventBus | None = None) -> None:
        self._events = events
        self._last_score: float | None = None

    def evaluate(
        self,
        plan: ExecutionSnapshot,
        signals: RuntimeSignals,
        *,
        catalog: dict[str, ModelProfile] | None = None,
    ) -> HealthReport:
        catalog = catalog or {}
        factors: dict[str, float] = {}
        reasons: list[str] = []

        # Model availability
        model_avail = 1.0 if signals.model_available else 0.0
        if plan.model in signals.model_health:
            model_avail = clamp01(signals.model_health[plan.model])
        profile = catalog.get(plan.model)
        if profile is not None:
            model_avail = min(model_avail, clamp01(profile.availability))
            if profile.health == HealthState.UNAVAILABLE:
                model_avail = 0.0
                reasons.append("model_profile_unavailable")
            elif profile.health == HealthState.UNHEALTHY:
                model_avail = min(model_avail, 0.3)
                reasons.append("model_profile_unhealthy")
        factors["model_availability"] = model_avail
        if model_avail < 0.5:
            reasons.append("model_unavailable")

        # Backend availability
        backend_avail = 1.0 if signals.backend_available else 0.0
        if plan.backend in signals.backend_health:
            backend_avail = clamp01(signals.backend_health[plan.backend])
        factors["backend_availability"] = backend_avail
        if backend_avail < 0.5:
            reasons.append("backend_unavailable")

        # Memory pressure (invert)
        mem_score = clamp01(1.0 - signals.memory_pressure)
        factors["memory"] = mem_score
        if signals.memory_pressure >= 0.85:
            reasons.append("memory_pressure")

        # Queue depth — soft degrade after depth 8
        queue_score = clamp01(1.0 - (signals.queue_depth / 16.0))
        factors["queue"] = queue_score
        if signals.queue_depth >= 8:
            reasons.append("queue_depth")

        # Latency SLO
        slo = max(signals.latency_slo_ms, 1.0)
        latency_score = clamp01(1.0 - (signals.latency_p99_ms / (slo * 1.5)))
        if signals.latency_p99_ms > slo:
            reasons.append("latency_slo_breach")
        factors["latency_slo"] = latency_score

        # Budget exhaustion
        budget_score = clamp01(signals.budget_remaining_ratio)
        if signals.budget_remaining_usd is not None and signals.budget_remaining_usd <= 0:
            budget_score = 0.0
            reasons.append("budget_exhausted")
        elif signals.budget_remaining_ratio < 0.1:
            reasons.append("budget_low")
        factors["budget"] = budget_score

        # Thread availability
        thread_score = 1.0 if signals.thread_available > 0 else 0.0
        if signals.thread_available < plan.thread_count:
            thread_score = clamp01(signals.thread_available / max(plan.thread_count, 1))
            reasons.append("thread_shortage")
        factors["threads"] = thread_score

        # Historical failures
        fail_score = clamp01(1.0 - (signals.historical_failures / 5.0))
        factors["history"] = fail_score
        if signals.historical_failures > 0:
            reasons.append("historical_failures")

        # Context compatibility
        ctx_score = 1.0
        if profile is not None and signals.context_tokens_needed > profile.context_length:
            ctx_score = 0.0
            reasons.append("context_incompatible")
        elif signals.context_tokens_needed > plan.context_length:
            ctx_score = 0.4
            reasons.append("context_plan_too_small")
        factors["context"] = ctx_score

        weights = {
            "model_availability": 0.20,
            "backend_availability": 0.15,
            "memory": 0.12,
            "queue": 0.08,
            "latency_slo": 0.15,
            "budget": 0.10,
            "threads": 0.05,
            "history": 0.10,
            "context": 0.05,
        }
        health_score = clamp01(
            sum(factors[k] * weights[k] for k in weights)
        )
        # Hard cap when primary model/backend is down — avoid healthy-looking averages
        if model_avail <= 0.0 or backend_avail <= 0.0:
            health_score = min(health_score, 0.34)

        state = HealthState.HEALTHY
        if model_avail <= 0 or backend_avail <= 0:
            state = HealthState.UNAVAILABLE
        elif health_score < 0.35:
            state = HealthState.UNHEALTHY
        elif health_score < 0.55:
            state = HealthState.DEGRADED

        model_components = [
            ComponentHealth(
                name=plan.model,
                kind="model",
                state=_state_from_score(model_avail),
                score=model_avail,
                reasons=[r for r in reasons if r.startswith("model")],
            )
        ]
        backend_components = [
            ComponentHealth(
                name=plan.backend,
                kind="backend",
                state=_state_from_score(backend_avail),
                score=backend_avail,
                reasons=[r for r in reasons if r.startswith("backend")],
            )
        ]

        report = HealthReport(
            health_score=health_score,
            state=state,
            model_health=model_components,
            backend_health=backend_components,
            factors=factors,
            reasons=reasons,
        )

        if self._events is not None and (
            self._last_score is None or abs(self._last_score - health_score) > 0.05
        ):
            self._events.emit(
                ev.HealthChanged(
                    execution_id=plan.execution_id or signals.execution_id,
                    model_id=plan.model,
                    health_score=health_score,
                    state=state.value,
                )
            )
        self._last_score = health_score
        return report


def _state_from_score(score: float) -> HealthState:
    if score <= 0.0:
        return HealthState.UNAVAILABLE
    if score < 0.35:
        return HealthState.UNHEALTHY
    if score < 0.55:
        return HealthState.DEGRADED
    return HealthState.HEALTHY
