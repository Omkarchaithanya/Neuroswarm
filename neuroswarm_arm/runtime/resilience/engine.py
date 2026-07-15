"""ResilienceEngine facade — continuous evaluate → alternative plan.

Never executes inference. Never schedules threads. Never owns ARMORA planning.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import events as ev
from .candidates import CandidateGenerator
from .constraints import ConstraintSolver
from .evaluator import ResilienceEvaluator
from .execution import AlternativeExecutionPlan, ExecutionSnapshot
from .health import HealthEngine
from .history import RecoveryHistory
from .metrics import ResilienceMetrics
from .models import (
    DecisionKind,
    ModelProfile,
    ResilienceDecision,
    RuntimeSignals,
)
from .planner import ResiliencePlanner
from .policy import PolicyEngine, ResiliencePolicy, default_policy
from .recovery import RecoveryOrchestrator
from .scoring import DeterministicScorer
from .validators import ResilienceValidator


class ResilienceEngine:
    """Runtime Model Resilience Engine — Kubernetes-style reconciliation for plans."""

    def __init__(
        self,
        *,
        policy_engine: PolicyEngine | None = None,
        catalog: dict[str, ModelProfile] | None = None,
        health: HealthEngine | None = None,
        candidates: CandidateGenerator | None = None,
        constraints: ConstraintSolver | None = None,
        scorer: DeterministicScorer | None = None,
        evaluator: ResilienceEvaluator | None = None,
        planner: ResiliencePlanner | None = None,
        recovery: RecoveryOrchestrator | None = None,
        history: RecoveryHistory | None = None,
        events: ev.EventBus | None = None,
        metrics: ResilienceMetrics | None = None,
        validator: ResilienceValidator | None = None,
        default_policy_obj: ResiliencePolicy | None = None,
    ) -> None:
        self.events = events or ev.EventBus()
        self.metrics = metrics or ResilienceMetrics()
        self.history = history or RecoveryHistory()
        self.catalog: dict[str, ModelProfile] = dict(catalog or {})
        self.policy_engine = policy_engine or PolicyEngine()
        self.health = health or HealthEngine(events=self.events)
        self.candidates = candidates or CandidateGenerator(events=self.events)
        self.constraints = constraints or ConstraintSolver()
        self.scorer = scorer or DeterministicScorer()
        self.evaluator = evaluator or ResilienceEvaluator()
        self.planner = planner or ResiliencePlanner()
        self.recovery = recovery or RecoveryOrchestrator(
            self.history, events=self.events
        )
        self.validator = validator or ResilienceValidator()
        self._default_policy = default_policy_obj or default_policy()
        if self.policy_engine.get(self._default_policy.policy_id) is None:
            self.policy_engine.register(self._default_policy)

    def register_profile(self, profile: ModelProfile) -> None:
        self.validator.validate_profile(profile)
        self.catalog[profile.model_id] = profile

    def register_policy(self, policy: ResiliencePolicy) -> None:
        self.validator.validate_policy(policy)
        self.policy_engine.register(policy)

    def evaluate(
        self,
        plan: ExecutionSnapshot,
        signals: RuntimeSignals,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> ResilienceDecision:
        """Reconcile active plan against health + policy → decision."""
        self.validator.validate_snapshot(plan)
        self.metrics.incr("health_evaluations")

        health = self.health.evaluate(plan, signals, catalog=self.catalog)
        policy = self.policy_engine.match(plan, signals, context=context)
        if policy is None:
            policy = self._default_policy
        else:
            self.metrics.incr("policy_match_count")
            self.events.emit(
                ev.PolicyMatched(
                    execution_id=plan.execution_id,
                    policy_id=policy.policy_id,
                    model_id=plan.model,
                )
            )

        should_transition, reasons = self.evaluator.should_transition(
            plan, signals, health, policy
        )
        if not should_transition:
            self.metrics.incr("continue_count")
            return ResilienceDecision(
                kind=DecisionKind.CONTINUE,
                policy_id=policy.policy_id,
                health_score=health.health_score,
                reasons=["healthy"],
            )

        self.events.emit(
            ev.FallbackTriggered(
                execution_id=plan.execution_id,
                policy_id=policy.policy_id,
                model_id=plan.model,
                reasons=reasons,
                health_score=health.health_score,
            )
        )

        generated = self.candidates.generate(plan, signals, policy, self.catalog)
        self.metrics.incr("candidate_count", len(generated))

        # Exclude identical current configuration; if model is down, drop same model
        generated = [
            c
            for c in generated
            if not (
                c.model_id == plan.model
                and c.backend == plan.backend
                and c.quant == plan.quant
                and c.context_length == plan.context_length
                and c.thread_count == plan.thread_count
                and c.reasoning_budget == plan.reasoning_budget
                and c.tools_enabled == plan.tools_enabled
                and c.cascade_strategy == plan.cascade_strategy
            )
        ]
        if not signals.model_available:
            generated = [c for c in generated if c.model_id != plan.model]
        if not signals.backend_available:
            generated = [c for c in generated if c.backend != plan.backend]

        filtered = self.constraints.filter(
            generated,
            plan=plan,
            signals=signals,
            policy=policy,
            catalog=self.catalog,
        )
        ranked = self.scorer.rank(
            filtered,
            plan=plan,
            signals=signals,
            policy=policy,
            catalog=self.catalog,
            health_score=health.health_score,
        )

        if not ranked:
            self.metrics.incr("degrade_notify_count")
            self.recovery.record_failure(
                plan, reason=";".join(reasons) or "no_valid_candidate", policy_id=policy.policy_id
            )
            self.metrics.record_fallback(success=False)
            return ResilienceDecision(
                kind=DecisionKind.DEGRADE_NOTIFY,
                policy_id=policy.policy_id,
                health_score=health.health_score,
                reasons=reasons + ["no_valid_candidate"],
            )

        winner = ranked[0]
        remaining = [c.candidate.model_id for c in ranked[1:]]
        alternative = self.planner.to_alternative_plan(
            winner, plan, reason=";".join(reasons), remaining_fallbacks=remaining
        )
        self.validator.validate_alternative(alternative)

        self.recovery.record_transition(
            plan, alternative, winner, success=True, reason=";".join(reasons)
        )
        self.metrics.record_fallback(
            success=True,
            quality_delta=alternative.quality_delta,
            latency_delta=alternative.latency_delta,
            cost_delta=alternative.cost_delta,
            backend_changed=alternative.backend != plan.backend,
            quant_changed=alternative.quant != plan.quant,
        )

        return ResilienceDecision(
            kind=DecisionKind.TRANSITION,
            policy_id=policy.policy_id,
            health_score=health.health_score,
            alternative=alternative,
            scored=winner,
            reasons=reasons,
        )

    def propose(
        self,
        plan: ExecutionSnapshot,
        signals: RuntimeSignals,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> AlternativeExecutionPlan | None:
        decision = self.evaluate(plan, signals, context=context)
        if decision.kind != DecisionKind.TRANSITION:
            return None
        alt = decision.alternative
        return alt if isinstance(alt, AlternativeExecutionPlan) else None

    async def aevaluate(
        self,
        plan: ExecutionSnapshot,
        signals: RuntimeSignals,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> ResilienceDecision:
        """Async-friendly wrapper (CPU-bound; no I/O)."""
        return self.evaluate(plan, signals, context=context)


def build_resilience_engine(
    *,
    policies: list[ResiliencePolicy] | None = None,
    catalog: dict[str, ModelProfile] | list[ModelProfile] | None = None,
    history: RecoveryHistory | None = None,
    events: ev.EventBus | None = None,
    metrics: ResilienceMetrics | None = None,
    experience: Any = None,
    performix: Any = None,
    external_policy: Any = None,
    default_policy_obj: ResiliencePolicy | None = None,
) -> ResilienceEngine:
    """Constructor DI factory — peer ports optional."""
    cat: dict[str, ModelProfile] = {}
    if isinstance(catalog, dict):
        cat = dict(catalog)
    elif isinstance(catalog, list):
        cat = {p.model_id: p for p in catalog}

    bus = events or ev.EventBus()
    hist = history or RecoveryHistory()
    policy_engine = PolicyEngine(policies, external=external_policy)
    recovery = RecoveryOrchestrator(
        hist, events=bus, experience=experience, performix=performix
    )
    engine = ResilienceEngine(
        policy_engine=policy_engine,
        catalog=cat,
        history=hist,
        events=bus,
        metrics=metrics or ResilienceMetrics(),
        recovery=recovery,
        default_policy_obj=default_policy_obj,
    )
    return engine
