"""Runtime Cost Intelligence facade + DI factory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .accounting import DefaultAccountingEngine
from .analyzer import DefaultCostAnalyzer
from .config import RCISRuntimeConfig, load_rcis_config
from .estimator import DefaultLiveCostEstimator, PsutilEnergySampler
from .feedback import PlannerFeedbackService
from .plugins import RCISPluginRegistry
from .predictor import DefaultCostPredictor
from .reports import ReportBuilder
from .repositories import BackendCostRepo, ModelTierRepo, QuantCostRepo, SpecStrategyRepo
from .schemas import (
    CostPrediction,
    ObservedRuntimeSignals,
    RequestContext,
    RuntimeCostReport,
    UnitEconomics,
)
from .tracker import CostSession, CostTracker


@dataclass
class RuntimeCostIntelligence:
    """ARMORA-owned RCIS — predict → track → estimate → analyze → persist → feedback."""

    config: RCISRuntimeConfig
    tracker: CostTracker
    estimator: DefaultLiveCostEstimator
    predictor: DefaultCostPredictor
    analyzer: DefaultCostAnalyzer
    persistence: Any
    telemetry: Any
    accounting: DefaultAccountingEngine
    feedback: PlannerFeedbackService
    reports: ReportBuilder
    registry: RCISPluginRegistry
    energy_sampler: PsutilEnergySampler

    async def predict(self, context: RequestContext) -> CostPrediction:
        if not self.config.enabled:
            return CostPrediction(
                request_id=context.request_id,
                execution_id=context.execution_id,
            )
        prediction = self.predictor.predict(context)
        self.persistence.write_prediction(prediction)
        return prediction

    def predict_sync(self, context: RequestContext) -> CostPrediction:
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.predict(context))
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(self.predict(context))).result()

    def open_session(
        self,
        context: RequestContext,
        *,
        prediction: CostPrediction | None = None,
    ) -> CostSession:
        return self.tracker.open(context, prediction=prediction)

    def record(self, execution_id: str, **kwargs: Any) -> CostSession | None:
        return self.tracker.record(execution_id, **kwargs)

    async def finalize(
        self,
        *,
        context: RequestContext | None = None,
        observed: ObservedRuntimeSignals | None = None,
        predicted: CostPrediction | None = None,
        execution_id: str = "",
    ) -> RuntimeCostReport:
        session = None
        if execution_id:
            session = self.tracker.close(execution_id)
        elif context is not None:
            session = self.tracker.close(context.execution_id)

        ctx = context or (session.context if session else RequestContext())
        obs = observed or (session.observed if session else ObservedRuntimeSignals())
        pred = predicted or (session.prediction if session else None)

        # Enrich memory/CPU from psutil when missing
        if obs.peak_memory_bytes <= 0 or obs.average_memory_bytes <= 0:
            rss = self.energy_sampler.sample_rss_bytes()
            if rss > 0:
                data = obs.model_dump()
                if data.get("peak_memory_bytes", 0) <= 0:
                    data["peak_memory_bytes"] = rss
                if data.get("average_memory_bytes", 0) <= 0:
                    data["average_memory_bytes"] = rss
                obs = ObservedRuntimeSignals.model_validate(data)
        if obs.avg_cpu_utilization <= 0:
            util = self.energy_sampler.sample_utilization()
            if util > 0:
                data = obs.model_dump()
                data["avg_cpu_utilization"] = util
                obs = ObservedRuntimeSignals.model_validate(data)

        hw = ctx.hardware.model_dump()
        breakdown = self.estimator.estimate(obs, hardware=hw)
        joules, watts = self.estimator.estimate_energy_joules(
            cpu_seconds=float(obs.cpu_seconds),
            thread_count=int(hw.get("thread_count", 1) or 1),
            avg_cpu_utilization=float(obs.avg_cpu_utilization),
            measured_joules=float(obs.energy_joules),
            watts_estimate=float(obs.watts_estimate),
        )
        carbon = joules * self.config.carbon_kg_per_joule

        report = self.analyzer.analyze(
            context=ctx,
            observed=obs,
            breakdown=breakdown,
            prediction=pred,
            energy_joules=joules,
            watts=watts,
            carbon_kg=carbon,
        )
        if self.config.enabled:
            self.persistence.write_report(report)
            self.telemetry.record_report(report)
        return report

    def finalize_sync(self, **kwargs: Any) -> RuntimeCostReport:
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.finalize(**kwargs))
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(self.finalize(**kwargs))).result()

    def unit_economics(self, *, limit: int = 200) -> UnitEconomics:
        reports = self.persistence.query_reports(limit=limit)
        return self.accounting.compute(reports)

    def comparison_bundle(self, *, limit: int = 200) -> Mapping[str, Any]:
        reports = self.persistence.query_reports(limit=limit)
        economics = self.accounting.compute(reports)
        return self.reports.bundle(reports, economics)

    def export_prometheus(self) -> str:
        if hasattr(self.telemetry, "export_prometheus"):
            return str(self.telemetry.export_prometheus())
        return ""

    def from_execution_accounting(
        self,
        accounting: Mapping[str, Any] | Any,
        *,
        context: RequestContext,
        prediction: CostPrediction | None = None,
        extras: Mapping[str, Any] | None = None,
    ) -> ObservedRuntimeSignals:
        """Bridge Budget ExecutionAccounting / DIPA metrics into ObservedRuntimeSignals."""
        if hasattr(accounting, "model_dump"):
            data = accounting.model_dump()
        else:
            data = dict(accounting)
        extras = dict(extras or {})
        return ObservedRuntimeSignals(
            prompt_tokens=int(data.get("prompt_tokens", 0)),
            completion_tokens=int(data.get("completion_tokens", 0)),
            reasoning_tokens=int(data.get("reasoning_tokens", 0)),
            cache_read_tokens=int(data.get("cache_read_tokens", 0)),
            cache_write_tokens=int(data.get("cache_write_tokens", 0)),
            accepted_speculative_tokens=int(extras.get("accepted_speculative_tokens", 0)),
            rejected_speculative_tokens=int(extras.get("rejected_speculative_tokens", 0)),
            kv_cache_hits=int(extras.get("kv_cache_hits", 0)),
            kv_cache_misses=int(extras.get("kv_cache_misses", 0)),
            kv_memory_bytes=float(data.get("kv_cache_bytes", extras.get("kv_memory_bytes", 0))),
            pages_shared=int(extras.get("pages_shared", 0)),
            migration_events=int(extras.get("migration_events", 0)),
            compression_savings_bytes=float(extras.get("compression_savings_bytes", 0)),
            cpu_seconds=float(data.get("cpu_seconds", 0)),
            wall_time_ms=float(data.get("wall_clock_ms", extras.get("wall_time_ms", 0))),
            planner_time_ms=float(extras.get("planner_time_ms", 0)),
            queue_time_ms=float(data.get("queue_wait_ms", 0)),
            execution_time_ms=float(data.get("execution_time_ms", 0)),
            streaming_time_ms=float(data.get("streaming_time_ms", 0)),
            peak_memory_bytes=float(data.get("peak_memory_bytes", 0)),
            average_memory_bytes=float(data.get("average_memory_bytes", 0)),
            energy_joules=float(data.get("estimated_energy_joules", extras.get("energy_joules", 0))),
            watts_estimate=float(extras.get("watts_estimate", 0)),
            tool_calls=int(data.get("tool_calls", 0)),
            retry_count=int(data.get("retries", extras.get("retry_count", 0))),
            quality_score=float(extras.get("quality_score", 1.0)),
            success=bool(extras.get("success", True)),
            failure_reason=str(extras.get("failure_reason", "")),
            verifier_overhead_ms=float(extras.get("verifier_overhead_ms", 0)),
            draft_model_cost_usd=float(extras.get("draft_model_cost_usd", 0)),
            verifier_cost_usd=float(extras.get("verifier_cost_usd", 0)),
            avg_cpu_utilization=float(extras.get("avg_cpu_utilization", 0)),
            extensions={**dict(context.extensions), **extras},
        )


def build_rcis(cfg: RCISRuntimeConfig | None = None) -> RuntimeCostIntelligence:
    config = cfg or load_rcis_config()
    registry = RCISPluginRegistry(config)
    persistence = registry.persistence()
    estimator = registry.cost_model()
    predictor = registry.predictor(history_provider=persistence)
    analyzer = registry.analyzer()
    telemetry = registry.telemetry()
    accounting = registry.accounting()
    tracker = CostTracker()
    feedback = PlannerFeedbackService(
        persistence,
        config,
        backend_repo=BackendCostRepo(persistence, config),
        quant_repo=QuantCostRepo(persistence, config),
        tier_repo=ModelTierRepo(persistence, config),
        spec_repo=SpecStrategyRepo(persistence, config),
    )
    return RuntimeCostIntelligence(
        config=config,
        tracker=tracker,
        estimator=estimator,
        predictor=predictor,
        analyzer=analyzer,
        persistence=persistence,
        telemetry=telemetry,
        accounting=accounting,
        feedback=feedback,
        reports=ReportBuilder(),
        registry=registry,
        energy_sampler=PsutilEnergySampler(config),
    )


def build_rcis_at(work_dir: Path | str) -> RuntimeCostIntelligence:
    return build_rcis(load_rcis_config(work_dir=Path(work_dir)))
