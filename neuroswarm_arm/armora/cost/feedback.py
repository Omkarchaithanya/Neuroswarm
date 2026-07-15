"""Planner feedback interfaces — never couple planner to database directly."""

from __future__ import annotations

from typing import Any

from .config import RCISRuntimeConfig
from .repositories import BackendCostRepo, ModelTierRepo, QuantCostRepo, SpecStrategyRepo
from .schemas import Objective, RankedChoices, WorkloadKey


class PlannerFeedbackService:
    """IPlannerFeedback implementation backed by repositories."""

    def __init__(
        self,
        persistence: Any,
        cfg: RCISRuntimeConfig,
        *,
        backend_repo: BackendCostRepo | None = None,
        quant_repo: QuantCostRepo | None = None,
        tier_repo: ModelTierRepo | None = None,
        spec_repo: SpecStrategyRepo | None = None,
    ) -> None:
        self.cfg = cfg
        self.backend_repo = backend_repo or BackendCostRepo(persistence, cfg)
        self.quant_repo = quant_repo or QuantCostRepo(persistence, cfg)
        self.tier_repo = tier_repo or ModelTierRepo(persistence, cfg)
        self.spec_repo = spec_repo or SpecStrategyRepo(persistence, cfg)

    async def lowest_cost_backend(self, workload: WorkloadKey) -> RankedChoices:
        del workload  # filters applied via future workload-aware repo extension
        return self.backend_repo.rank_by_cost()

    async def lowest_latency_quant(self, model: str) -> RankedChoices:
        return self.quant_repo.rank_by_latency(model=model)

    async def best_model_tier(self, objective: Objective) -> RankedChoices:
        return self.tier_repo.rank(objective)

    async def best_spec_strategy(self, workload: WorkloadKey) -> RankedChoices:
        return self.spec_repo.rank(workload)

    # Sync helpers for non-async callers (DIPA planners)
    def lowest_cost_backend_sync(self, workload: WorkloadKey | None = None) -> RankedChoices:
        return self.backend_repo.rank_by_cost()

    def lowest_latency_quant_sync(self, model: str = "") -> RankedChoices:
        return self.quant_repo.rank_by_latency(model=model)
