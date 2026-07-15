"""Budget service facade + factory — composition root for ARMORA budget."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .config import BudgetRuntimeConfig, load_budget_config
from .envelope import BudgetEnvelope
from .estimator import DefaultEstimator
from .lifecycle import BudgetLifecycle
from .optimizer import BudgetOptimizer
from .plugins import BudgetPluginRegistry
from .policy import PolicyEngine
from .reports import ReportBuilder, ReportBundle
from .schemas import AdmitDecision, AffordDecision, PlanAction
from .tracker import BudgetRuntimeState, BudgetTracker
from .validator import BudgetValidator


@dataclass
class BudgetService:
    config: BudgetRuntimeConfig
    tracker: BudgetTracker
    lifecycle: BudgetLifecycle
    optimizer: BudgetOptimizer
    estimator: DefaultEstimator
    telemetry: Any
    persistence: Any
    registry: BudgetPluginRegistry

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
        return await self.lifecycle.create_and_freeze(
            request_id=request_id,
            tenant_id=tenant_id,
            agent_role=agent_role,
            agent_id=agent_id,
            workflow=workflow,
            overrides=overrides,
            projected=projected,
        )

    def create_and_freeze_sync(
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
        import asyncio

        coro = self.create_and_freeze(
            request_id=request_id,
            tenant_id=tenant_id,
            agent_role=agent_role,
            agent_id=agent_id,
            workflow=workflow,
            overrides=overrides,
            projected=projected,
        )
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        # Already in async context — run in a dedicated thread to avoid nest conflicts
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    def can_afford(self, envelope_id: str, action: PlanAction) -> AffordDecision:
        state = self.tracker.get_state(envelope_id)
        return self.optimizer.can_afford(state, action)

    async def finalize(self, envelope_id: str, **kwargs: Any) -> ReportBundle:
        return await self.lifecycle.finalize(envelope_id, **kwargs)

    def remaining_cost_usd(self, envelope_id: str) -> float:
        return self.tracker.cost_remaining(envelope_id)

    def export_prometheus(self) -> str:
        if hasattr(self.telemetry, "export_prometheus"):
            return str(self.telemetry.export_prometheus())
        return ""


def build_budget_service(
    cfg: BudgetRuntimeConfig | None = None,
    *,
    okf_root: Path | None = None,
) -> BudgetService:
    config = cfg or load_budget_config()
    registry = BudgetPluginRegistry(config)
    cost_model = registry.cost_model()
    energy_model = registry.energy_model()
    estimator = registry.estimator(cost_model=cost_model, energy_model=energy_model)
    persistence = registry.persistence()
    telemetry = registry.telemetry()
    policy_compiler = registry.policy_compiler(okf_root=okf_root)
    policy = PolicyEngine(policy_compiler)
    tracker = BudgetTracker()
    validator = BudgetValidator()
    optimizer = BudgetOptimizer(config, validator=validator, estimator=estimator)
    reports = ReportBuilder()
    lifecycle = BudgetLifecycle(
        policy=policy,
        validator=validator,
        optimizer=optimizer,
        tracker=tracker,
        reports=reports,
        persistence=persistence,
        telemetry=telemetry,
        config=config,
    )
    return BudgetService(
        config=config,
        tracker=tracker,
        lifecycle=lifecycle,
        optimizer=optimizer,
        estimator=estimator,
        telemetry=telemetry,
        persistence=persistence,
        registry=registry,
    )
