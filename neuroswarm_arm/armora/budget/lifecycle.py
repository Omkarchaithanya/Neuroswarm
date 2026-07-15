"""Budget lifecycle state machine."""

from __future__ import annotations

from typing import Any, Mapping

from .envelope import BudgetEnvelope, build_envelope_from_template
from .optimizer import BudgetOptimizer
from .policy import PolicyEngine
from .reports import ReportBuilder, ReportBundle
from .schemas import AdmitDecision, ChargebackTags, LifecyclePhase
from .tracker import BudgetRuntimeState, BudgetTracker
from .validator import BudgetValidator


class BudgetLifecycle:
    def __init__(
        self,
        *,
        policy: PolicyEngine,
        validator: BudgetValidator,
        optimizer: BudgetOptimizer,
        tracker: BudgetTracker,
        reports: ReportBuilder,
        persistence: Any,
        telemetry: Any,
        config: Any,
    ) -> None:
        self.policy = policy
        self.validator = validator
        self.optimizer = optimizer
        self.tracker = tracker
        self.reports = reports
        self.persistence = persistence
        self.telemetry = telemetry
        self.config = config

    async def create_and_freeze(
        self,
        *,
        request_id: str,
        tenant_id: str = "",
        agent_role: str = "default",
        agent_id: str = "",
        workflow: str = "chat",
        overrides: Mapping[str, Any] | None = None,
        projected: Mapping[str, float] | None = None,
    ) -> tuple[BudgetEnvelope, BudgetRuntimeState, AdmitDecision]:
        with self.telemetry.span("budget.lifecycle.create") if hasattr(self.telemetry, "span") else _null():
            template = self.policy.compile(
                agent_role=agent_role, tenant_id=tenant_id, overrides=overrides
            )
            envelope = build_envelope_from_template(
                template,
                self.config,
                request_id=request_id,
                tenant_id=tenant_id,
                agent_id=agent_id,
                workflow=workflow,
            )

        with self.telemetry.span("budget.lifecycle.validate") if hasattr(self.telemetry, "span") else _null():
            decision = self.validator.validate_envelope(envelope, projected=projected)

        # Temporary state for optimizer before freeze
        draft_state = BudgetRuntimeState(
            envelope_id=str(envelope.envelope_id),
            phase=LifecyclePhase.VALIDATE,
            categories={k: v.model_copy(deep=True) for k, v in envelope.categories.items()},
        )
        if projected:
            for k, v in projected.items():
                if k in draft_state.categories:
                    draft_state.categories[k].projected = float(v)

        actions: list[str] = []
        if not decision.accepted or decision.soft_warnings:
            with self.telemetry.span("budget.lifecycle.optimize") if hasattr(self.telemetry, "span") else _null():
                opt = self.optimizer.optimize(
                    envelope, draft_state, projected=projected
                )
                decision = opt.decision
                actions = opt.actions_taken
                for a in actions:
                    if hasattr(self.telemetry, "record_degrade"):
                        self.telemetry.record_degrade(a)
                # Apply adjusted limits back onto envelope categories before freeze
                for name, cat in draft_state.categories.items():
                    if name in envelope.categories:
                        envelope.categories[name].limit = float(cat.limit)

        self.telemetry.record_admit(
            accepted=decision.accepted, tenant=tenant_id, agent=agent_id
        )
        if not decision.accepted:
            envelope_rejected = envelope  # unfrozen reject artifact
            state = BudgetRuntimeState(
                envelope_id=str(envelope.envelope_id),
                phase=LifecyclePhase.REJECTED,
                categories={k: v.model_copy(deep=True) for k, v in envelope.categories.items()},
                reject_reason="; ".join(decision.hard_failures),
            )
            return envelope_rejected, state, decision

        with self.telemetry.span("budget.lifecycle.freeze") if hasattr(self.telemetry, "span") else _null():
            frozen = envelope.freeze()
            state = self.tracker.register(frozen)
            state.degrade_actions.extend(actions)
            for name, cat in state.categories.items():
                self.telemetry.record_remaining(name, cat.remaining)
            return frozen, state, decision

    async def finalize(
        self,
        envelope_id: str,
        *,
        chargeback: ChargebackTags | None = None,
    ) -> ReportBundle:
        envelope = self.tracker.get_envelope(envelope_id)
        state = self.tracker.get_state(envelope_id)
        violations = self.tracker.check_violations(envelope_id)
        for v in violations:
            self.telemetry.record_violation(v["dim"], v["hardness"])
        for dim, err in state.estimate_errors.items():
            self.telemetry.record_estimate_error(dim, err)

        with self.telemetry.span("budget.lifecycle.report") if hasattr(self.telemetry, "span") else _null():
            bundle = self.reports.build(envelope, state, chargeback=chargeback)
            self.telemetry.record_efficiency(
                tokens_per_usd=bundle.telemetry.tokens_per_usd,
                tokens_per_watt=bundle.telemetry.tokens_per_watt,
            )

        with self.telemetry.span("budget.lifecycle.persist") if hasattr(self.telemetry, "span") else _null():
            self.persistence.write_envelope(
                envelope_id,
                {
                    **envelope.to_public_dict(),
                    "state": state.snapshot(),
                },
            )
            for rtype, payload in bundle.as_dict().items():
                self.persistence.write_report(envelope_id, rtype, payload)
            self.tracker.set_phase(envelope_id, LifecyclePhase.DONE)
        return bundle


class _NullCtx:
    def __enter__(self) -> "_NullCtx":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _null() -> _NullCtx:
    return _NullCtx()
