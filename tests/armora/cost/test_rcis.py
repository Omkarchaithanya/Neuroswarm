"""RCIS unit / estimator / prediction / telemetry / persistence / feedback tests."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from neuroswarm_arm.armora.cost import (
    Objective,
    ObservedRuntimeSignals,
    RequestContext,
    WorkloadKey,
    build_rcis,
    load_rcis_config,
)
from neuroswarm_arm.armora.cost.accounting import DefaultAccountingEngine
from neuroswarm_arm.armora.cost.analyzer import DefaultCostAnalyzer
from neuroswarm_arm.armora.cost.arop_provider import RCISObservationProvider
from neuroswarm_arm.armora.cost.estimator import DefaultLiveCostEstimator
from neuroswarm_arm.armora.cost.persistence import JsonPersistence, SqlitePersistence
from neuroswarm_arm.armora.cost.predictor import DefaultCostPredictor
from neuroswarm_arm.armora.cost.reports import ReportBuilder
from neuroswarm_arm.armora.cost.schemas import LiveCostBreakdown
from neuroswarm_arm.armora.cost.telemetry import InMemoryCostTelemetry
from neuroswarm_arm.evolution.models.observation import TimeWindow

_ROOT = Path(__file__).resolve().parents[3] / "work" / "test_rcis"


def _work() -> Path:
    path = _ROOT / uuid.uuid4().hex[:12]
    path.mkdir(parents=True, exist_ok=True)
    return path


def _rcis(work: Path | None = None):
    root = work or _work()
    cfg = load_rcis_config(work_dir=root)
    cfg.persistence = "sqlite"
    return build_rcis(cfg)


def _context(**kwargs):
    base = dict(
        request_id="req-1",
        execution_id="exec-1",
        workflow_id="wf-1",
        agent_id="agent-a",
        model="llama-3b",
        model_tier="tier2",
        backend="llama.cpp",
        quantization="q4_k_m",
        prompt_token_estimate=100,
    )
    base.update(kwargs)
    return RequestContext(**base)


def _observed(**kwargs):
    base = dict(
        prompt_tokens=100,
        completion_tokens=50,
        reasoning_tokens=10,
        cpu_seconds=2.0,
        wall_time_ms=1000.0,
        execution_time_ms=900.0,
        peak_memory_bytes=1_000_000_000,
        average_memory_bytes=800_000_000,
        kv_memory_bytes=100_000_000,
        kv_cache_hits=8,
        kv_cache_misses=2,
        accepted_speculative_tokens=20,
        rejected_speculative_tokens=5,
        success=True,
        quality_score=0.9,
    )
    base.update(kwargs)
    return ObservedRuntimeSignals(**base)


def test_config_loads_rates():
    work = _work()
    cfg = load_rcis_config(work_dir=work)
    assert cfg.usd_per_1k_prompt > 0
    assert cfg.work_dir.exists()


def test_estimator_live_breakdown():
    cfg = load_rcis_config(work_dir=_work())
    est = DefaultLiveCostEstimator(cfg)
    breakdown = est.estimate(_observed())
    assert isinstance(breakdown, LiveCostBreakdown)
    assert breakdown.total_runtime_cost > 0
    assert breakdown.prompt_cost > 0
    assert breakdown.completion_cost > 0


def test_estimator_energy_fallback():
    cfg = load_rcis_config(work_dir=_work())
    est = DefaultLiveCostEstimator(cfg)
    joules, watts = est.estimate_energy_joules(cpu_seconds=2.0, thread_count=4)
    assert joules > 0
    assert watts > 0


def test_predictor_returns_expectations():
    cfg = load_rcis_config(work_dir=_work())
    pred = DefaultCostPredictor(cfg).predict(_context())
    assert pred.expected_latency_ms > 0
    assert pred.expected_cost_usd > 0
    assert pred.expected_prompt_tokens == 100


def test_full_predict_finalize_loop():
    rcis = _rcis()
    ctx = _context()
    pred = rcis.predict_sync(ctx)
    rcis.open_session(ctx, prediction=pred)
    report = rcis.finalize_sync(context=ctx, observed=_observed(), predicted=pred)
    assert report.execution_id == "exec-1"
    assert report.estimated_dollars > 0
    assert report.prediction is not None
    assert report.prediction_errors is not None
    assert report.total_tokens == 160
    assert 0.0 <= report.kv_reuse_ratio <= 1.0
    assert report.schema_version == "1.0.0"


def test_prediction_error_computed():
    rcis = _rcis()
    ctx = _context()
    pred = rcis.predict_sync(ctx)
    report = rcis.finalize_sync(
        context=ctx, observed=_observed(wall_time_ms=5000), predicted=pred
    )
    assert report.prediction_errors is not None
    assert report.prediction_errors.latency_error != 0.0


def test_sqlite_persistence_roundtrip():
    work = _work()
    store = SqlitePersistence(work)
    rcis = _rcis(work)
    ctx = _context(execution_id="exec-p")
    pred = rcis.predict_sync(ctx)
    report = rcis.finalize_sync(context=ctx, observed=_observed(), predicted=pred)
    rows = store.query_reports(backend="llama.cpp", limit=10)
    assert any(r.report_id == report.report_id for r in rows)
    preds = store.query_predictions(request_id="req-1")
    assert preds


def test_json_persistence():
    work = _work() / "json"
    store = JsonPersistence(work)
    cfg = load_rcis_config(work_dir=work)
    cfg.persistence = "json"
    rcis = build_rcis(cfg)
    ctx = _context(execution_id="exec-j")
    report = rcis.finalize_sync(context=ctx, observed=_observed())
    rows = store.query_reports(limit=5)
    assert any(r.report_id == report.report_id for r in rows)


def test_telemetry_exports_runtime_metrics():
    tel = InMemoryCostTelemetry()
    rcis = _rcis()
    report = rcis.finalize_sync(context=_context(execution_id="exec-t"), observed=_observed())
    tel.record_report(report)
    text = tel.export_prometheus()
    assert "runtime_cost_total" in text
    assert "runtime_cpu_seconds" in text
    assert "runtime_kv_reuse" in text


def test_planner_feedback_ranks_backends():
    rcis = _rcis()
    for i, backend in enumerate(["llama.cpp", "vllm", "sglang", "llama.cpp"]):
        ctx = _context(execution_id=f"e{i}", backend=backend)
        obs = _observed(
            completion_tokens=10 if backend == "llama.cpp" else 200,
            wall_time_ms=100 if backend == "llama.cpp" else 2000,
        )
        rcis.finalize_sync(context=ctx, observed=obs)
    ranked = rcis.feedback.lowest_cost_backend_sync(WorkloadKey(intent="chat"))
    assert ranked.choices
    assert ranked.choices[0].key in {"llama.cpp", "vllm", "sglang"}


def test_quant_and_tier_feedback():
    rcis = _rcis()
    for q in ("q4_k_m", "q8_0", "fp16"):
        ctx = _context(execution_id=f"q-{q}", quantization=q)
        rcis.finalize_sync(
            context=ctx,
            observed=_observed(wall_time_ms=100 if q == "q4_k_m" else 800),
        )
    quant = rcis.feedback.lowest_latency_quant_sync("llama-3b")
    assert quant.choices
    import asyncio

    tier = asyncio.run(rcis.feedback.best_model_tier(Objective.COST))
    assert tier.choices


def test_accounting_unit_economics():
    rcis = _rcis()
    for i in range(3):
        rcis.finalize_sync(
            context=_context(execution_id=f"a{i}", agent_id="agent-a", workflow_id="wf"),
            observed=_observed(),
        )
    eco = rcis.unit_economics()
    assert eco.cost_per_request > 0
    assert "llama.cpp" in eco.cost_per_backend
    assert "q4_k_m" in eco.cost_per_quantization


def test_comparison_reports():
    rcis = _rcis()
    for backend in ("llama.cpp", "vllm"):
        rcis.finalize_sync(
            context=_context(execution_id=f"c-{backend}", backend=backend),
            observed=_observed(),
        )
    bundle = rcis.comparison_bundle()
    assert bundle["backend"]["rows"]
    assert bundle["speculation"]["samples"] >= 1
    assert bundle["kv"]["total_hits"] >= 1
    assert bundle["energy"]["mean_joules"] >= 0


def test_report_builder_known_dims():
    builder = ReportBuilder()
    assert "llama.cpp" in builder.KNOWN_BACKENDS
    assert "q4_k_m" in builder.KNOWN_QUANTS


def test_immutable_report():
    rcis = _rcis()
    report = rcis.finalize_sync(context=_context(execution_id="imm"), observed=_observed())
    with pytest.raises(Exception):
        report.estimated_dollars = 99.0  # type: ignore[misc]


def test_arop_observation_provider():
    rcis = _rcis()
    rcis.finalize_sync(context=_context(execution_id="arop-1"), observed=_observed())
    provider = RCISObservationProvider(rcis)
    health = provider.health()
    assert health.healthy
    snap = provider.snapshot()
    assert isinstance(snap.aggregate, dict)
    events = provider.collect(TimeWindow.last_seconds(3600))
    assert events
    assert "asi" in events[0].payload
    metrics = provider.metrics()
    assert isinstance(metrics, dict)


def test_from_execution_accounting_bridge():
    rcis = _rcis()
    ctx = _context(execution_id="bridge")
    obs = rcis.from_execution_accounting(
        {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "cpu_seconds": 1.0,
            "wall_clock_ms": 400,
            "peak_memory_bytes": 1000,
        },
        context=ctx,
        extras={"kv_cache_hits": 3, "kv_cache_misses": 1},
    )
    assert obs.prompt_tokens == 10
    assert obs.kv_cache_hits == 3


def test_tracker_session():
    rcis = _rcis()
    ctx = _context(execution_id="sess")
    rcis.open_session(ctx)
    rcis.record("sess", prompt_tokens=12)
    closed = rcis.tracker.close("sess")
    assert closed is not None
    assert closed.closed
    assert closed.observed.prompt_tokens == 12


def test_disabled_rcis_still_returns_report():
    work = _work()
    cfg = load_rcis_config(work_dir=work)
    cfg.enabled = False
    rcis = build_rcis(cfg)
    report = rcis.finalize_sync(context=_context(execution_id="off"), observed=_observed())
    assert report.estimated_dollars >= 0


def test_analyzer_speculation_ratio():
    analyzer = DefaultCostAnalyzer()
    cfg = load_rcis_config(work_dir=_work())
    est = DefaultLiveCostEstimator(cfg)
    obs = _observed(accepted_speculative_tokens=8, rejected_speculative_tokens=2)
    breakdown = est.estimate(obs)
    report = analyzer.analyze(
        context=_context(),
        observed=obs,
        breakdown=breakdown,
        prediction=None,
        energy_joules=10.0,
        watts=5.0,
        carbon_kg=0.0,
    )
    assert report.speculation_acceptance_ratio == pytest.approx(0.8)


def test_accounting_empty():
    eco = DefaultAccountingEngine().compute([])
    assert eco.cost_per_request == 0.0


def test_rcis_prometheus_export():
    rcis = _rcis()
    rcis.finalize_sync(context=_context(execution_id="prom"), observed=_observed())
    text = rcis.export_prometheus()
    assert "runtime_cost_total" in text
