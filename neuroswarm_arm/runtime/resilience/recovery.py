"""Recovery orchestrator — records transitions; never executes inference."""

from __future__ import annotations

from . import events as ev
from ._utils import new_id
from .execution import AlternativeExecutionPlan, ExecutionSnapshot
from .history import RecoveryHistory
from .interfaces import IExperienceStorePort, IPerformixResiliencePort
from .models import DecisionKind, RecoveryRecord, ScoredCandidate


class RecoveryOrchestrator:
    """Record recovery transitions + emit events / experience refs."""

    def __init__(
        self,
        history: RecoveryHistory | None = None,
        *,
        events: ev.EventBus | None = None,
        experience: IExperienceStorePort | None = None,
        performix: IPerformixResiliencePort | None = None,
    ) -> None:
        self.history = history or RecoveryHistory()
        self._events = events
        self._experience = experience
        self._performix = performix

    def record_transition(
        self,
        plan: ExecutionSnapshot,
        alternative: AlternativeExecutionPlan,
        scored: ScoredCandidate | None,
        *,
        success: bool = True,
        reason: str = "",
    ) -> RecoveryRecord:
        experience_ref: str | None = None
        if self._experience is not None:
            try:
                experience_ref = self._experience.store_snapshot(
                    {
                        "kind": "rmre_recovery",
                        "plan": plan.model_dump(mode="json"),
                        "alternative": alternative.model_dump(mode="json"),
                    }
                )
            except Exception:
                experience_ref = None

        record = RecoveryRecord(
            record_id=new_id("rec_"),
            execution_id=plan.execution_id,
            fallback_reason=reason or alternative.reason,
            previous_model=alternative.previous_model or plan.model,
            new_model=alternative.model,
            previous_backend=alternative.previous_backend or plan.backend,
            new_backend=alternative.backend,
            previous_quant=alternative.previous_quant or plan.quant,
            new_quant=alternative.quant,
            quality_delta=alternative.quality_delta,
            latency_delta=alternative.latency_delta,
            budget_delta=alternative.budget_delta,
            recovery_success=success,
            decision=DecisionKind.TRANSITION if success else DecisionKind.DEGRADE_NOTIFY,
            experience_ref=experience_ref,
            metadata={
                "score": scored.score if scored else alternative.score,
                "plan_id": alternative.plan_id,
            },
        )
        self.history.append(record)

        if self._performix is not None:
            try:
                self._performix.record_resilience_sample(
                    plan.execution_id,
                    quality_delta=alternative.quality_delta,
                    latency_delta=alternative.latency_delta,
                    cost_delta=alternative.cost_delta,
                )
            except Exception:
                pass

        if self._events is not None:
            evt = (
                ev.RecoveryCompleted(
                    execution_id=plan.execution_id,
                    model_id=alternative.model,
                    previous_model=record.previous_model,
                    success=True,
                )
                if success
                else ev.RecoveryFailed(
                    execution_id=plan.execution_id,
                    model_id=plan.model,
                    reason=reason or alternative.reason,
                )
            )
            self._events.emit(evt)

        return record

    def record_failure(
        self,
        plan: ExecutionSnapshot,
        *,
        reason: str,
        policy_id: str | None = None,
    ) -> RecoveryRecord:
        record = RecoveryRecord(
            record_id=new_id("rec_"),
            execution_id=plan.execution_id,
            fallback_reason=reason,
            previous_model=plan.model,
            new_model=plan.model,
            previous_backend=plan.backend,
            new_backend=plan.backend,
            previous_quant=plan.quant,
            new_quant=plan.quant,
            recovery_success=False,
            decision=DecisionKind.DEGRADE_NOTIFY,
            metadata={"policy_id": policy_id},
        )
        self.history.append(record)
        if self._events is not None:
            self._events.emit(
                ev.RecoveryFailed(
                    execution_id=plan.execution_id,
                    policy_id=policy_id,
                    model_id=plan.model,
                    reason=reason,
                )
            )
        return record
