"""Accounting, planner afford, telemetry, plugins, load tests."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from neuroswarm_arm.armora.budget import (
    ArmoraBudgetPolicy,
    BudgetConfig,
    DefaultEstimator,
    PlanAction,
    build_budget_service,
    load_budget_config,
    register_cost_model,
)
from neuroswarm_arm.armora.budget.accounting import ExecutionAccounting
from neuroswarm_arm.armora.budget.dipa_gate import BudgetAffordGate
from neuroswarm_arm.armora.budget.rtg_adapter import ReasoningBudgetView
from neuroswarm_arm.armora.budget.schemas import DimensionDelta, ResourceProjection


@pytest.fixture
def svc(request):
    root = Path("work") / "test_budget" / request.node.name
    root.mkdir(parents=True, exist_ok=True)
    cfg = load_budget_config(work_dir=root)
    return build_budget_service(cfg)


def test_execution_accounting_totals():
    acc = ExecutionAccounting()
    acc.record_tokens(prompt=10, completion=5, reasoning=3)
    acc.record_memory(1000)
    acc.record_memory(2000)
    acc.record_cost(0.01)
    acc.record_energy(2.5)
    assert acc.total_tokens == 18
    assert acc.peak_memory_bytes == 2000
    assert acc.average_memory_bytes == 1500
    d = acc.as_dimension_delta()
    assert d["tokens_total"] == 18


def test_planner_afford_gate(svc):
    env, _, _ = svc.create_and_freeze_sync(request_id="p1", agent_role="chat")
    gate = BudgetAffordGate(svc)
    tier = gate.select_affordable_tier(str(env.envelope_id), preferred=1, maximum=3)
    assert 1 <= tier <= 3
    meta = gate.guard_metadata(
        str(env.envelope_id), {"preferred_model_tier": 3, "quantization": "fp16"}
    )
    assert "budget_envelope_id" in meta


def test_rtg_adapter_view(svc):
    env, _, _ = svc.create_and_freeze_sync(request_id="rtg1", agent_role="chat")
    view = ReasoningBudgetView(str(env.envelope_id), svc.tracker)
    before = view.remaining_tokens
    view.consume(10, latency_ms=5.0, cost_usd=0.0001)
    assert view.remaining_tokens <= before
    assert view.latency_spent_ms >= 5.0
    legacy = view.as_legacy_dict()
    assert legacy["envelope_id"] == str(env.envelope_id)


def test_armora_budget_policy_compat(svc):
    policy = ArmoraBudgetPolicy(BudgetConfig(max_cost_usd=0.05), service=svc)
    assert policy.admit(1024)
    assert policy.charge(0.001)
    assert not policy.charge(1.0)
    st = policy.status()
    assert st["spent_usd"] == pytest.approx(0.001)
    assert st["envelope_id"]


def test_estimator_kv_and_actions(svc):
    est: DefaultEstimator = svc.estimator
    kv = est.project_kv(layers=32, kv_heads=8, head_dim=128, seq_len=2048)
    assert kv.p50.get("kv_bytes") > 0
    for action in (
        PlanAction.tier(2),
        PlanAction.quant("q4"),
        PlanAction.reasoning(128),
        PlanAction.speculate(8),
        PlanAction.tool_call(0.001),
        PlanAction.retry(),
        PlanAction.expand_context(512),
        PlanAction.batch(2),
    ):
        proj = est.project_action(action)
        assert isinstance(proj, ResourceProjection)


def test_telemetry_prometheus(svc):
    svc.telemetry.record_admit(accepted=True)
    svc.telemetry.record_remaining("cost_usd", 0.04)
    svc.telemetry.record_violation("cost_usd", "hard")
    svc.telemetry.record_degrade("cut_reasoning")
    svc.telemetry.record_efficiency(tokens_per_usd=1000.0, tokens_per_watt=50.0)
    text = svc.export_prometheus()
    assert "budget_admit_total" in text
    assert "budget_tokens_per_usd" in text


def test_plugin_register_cost_model(request):
    @register_cost_model("test_zero")
    class ZeroCost:
        def __init__(self, cfg):
            self.cfg = cfg

        def project(self, op, hardware=None, cache_state=None):
            return ResourceProjection(
                p50=DimensionDelta(values={"cost_usd": 0.0}),
                p90=DimensionDelta(values={"cost_usd": 0.0}),
            )

    root = Path("work") / "test_budget" / request.node.name
    root.mkdir(parents=True, exist_ok=True)
    cfg = load_budget_config(work_dir=root)
    cfg.cost_model = "test_zero"
    svc = build_budget_service(cfg)
    proj = svc.estimator.cost_model.project({"prompt_tokens": 1000})
    assert proj.p50.get("cost_usd") == 0.0


def test_json_persistence(request):
    root = Path("work") / "test_budget" / request.node.name
    root.mkdir(parents=True, exist_ok=True)
    cfg = load_budget_config(work_dir=root)
    cfg.persistence = "json"
    svc = build_budget_service(cfg)
    env, _, _ = svc.create_and_freeze_sync(request_id="j1", agent_role="chat")
    svc.persistence.write_envelope(str(env.envelope_id), env.to_public_dict())
    hist = svc.persistence.query_history(limit=5)
    assert hist


def test_load_performance(svc):
    n = 50
    t0 = time.perf_counter()
    for i in range(n):
        env, _, _ = svc.create_and_freeze_sync(request_id=f"L{i}", agent_role="chat")
        svc.tracker.consume(str(env.envelope_id), {"cost_usd": 0.00001})
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0
