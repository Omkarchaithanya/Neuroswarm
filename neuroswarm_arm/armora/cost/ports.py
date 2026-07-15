"""Ports / Protocols for hexagonal RCIS architecture."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from .schemas import (
    CostPrediction,
    LiveCostBreakdown,
    Objective,
    ObservedRuntimeSignals,
    RankedChoices,
    RequestContext,
    RuntimeCostReport,
    UnitEconomics,
    WorkloadKey,
)


@runtime_checkable
class ILiveCostEstimator(Protocol):
    def estimate(
        self,
        observed: ObservedRuntimeSignals,
        *,
        hardware: Mapping[str, Any] | None = None,
    ) -> LiveCostBreakdown: ...

    def estimate_energy_joules(
        self,
        *,
        cpu_seconds: float,
        thread_count: int = 1,
        avg_cpu_utilization: float = 0.0,
        measured_joules: float = 0.0,
        watts_estimate: float = 0.0,
    ) -> tuple[float, float]: ...


@runtime_checkable
class ICostPredictor(Protocol):
    def predict(self, context: RequestContext) -> CostPrediction: ...


@runtime_checkable
class ICostAnalyzer(Protocol):
    def analyze(
        self,
        *,
        context: RequestContext,
        observed: ObservedRuntimeSignals,
        breakdown: LiveCostBreakdown,
        prediction: CostPrediction | None,
        energy_joules: float,
        watts: float,
        carbon_kg: float,
    ) -> RuntimeCostReport: ...


@runtime_checkable
class ICostPersistence(Protocol):
    def write_prediction(self, prediction: CostPrediction) -> None: ...

    def write_report(self, report: RuntimeCostReport) -> None: ...

    def query_reports(
        self,
        *,
        tenant_id: str = "",
        backend: str = "",
        quantization: str = "",
        model_tier: str = "",
        agent_id: str = "",
        workflow_id: str = "",
        limit: int = 200,
    ) -> list[RuntimeCostReport]: ...

    def query_predictions(self, *, request_id: str = "", limit: int = 100) -> list[CostPrediction]: ...


@runtime_checkable
class ICostTelemetry(Protocol):
    def record_report(self, report: RuntimeCostReport) -> None: ...

    def record_prediction_error(self, dim: str, error: float) -> None: ...

    def export_prometheus(self) -> str: ...

    def snapshot(self) -> Mapping[str, Any]: ...


@runtime_checkable
class IAccountingEngine(Protocol):
    def compute(self, reports: list[RuntimeCostReport]) -> UnitEconomics: ...


@runtime_checkable
class IPlannerFeedback(Protocol):
    async def lowest_cost_backend(self, workload: WorkloadKey) -> RankedChoices: ...

    async def lowest_latency_quant(self, model: str) -> RankedChoices: ...

    async def best_model_tier(self, objective: Objective) -> RankedChoices: ...

    async def best_spec_strategy(self, workload: WorkloadKey) -> RankedChoices: ...


@runtime_checkable
class IBackendCostRepo(Protocol):
    def rank_by_cost(self, *, limit: int = 50) -> RankedChoices: ...

    def rank_by_latency(self, *, limit: int = 50) -> RankedChoices: ...


@runtime_checkable
class IQuantCostRepo(Protocol):
    def rank_by_latency(self, *, model: str = "", limit: int = 50) -> RankedChoices: ...

    def rank_by_cost(self, *, model: str = "", limit: int = 50) -> RankedChoices: ...


@runtime_checkable
class IModelTierRepo(Protocol):
    def rank(self, objective: Objective, *, limit: int = 50) -> RankedChoices: ...


@runtime_checkable
class ISpecStrategyRepo(Protocol):
    def rank(self, workload: WorkloadKey, *, limit: int = 50) -> RankedChoices: ...


@runtime_checkable
class IDashboardProvider(Protocol):
    def panels(self) -> list[Mapping[str, Any]]: ...

    def name(self) -> str: ...
