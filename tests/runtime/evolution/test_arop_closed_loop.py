"""AROP closed loop — Performix reflection, quant preference, CostRouter tier floor."""

from __future__ import annotations

import pytest

from neuroswarm_arm.evolution.deployment.adapters import (
    AQRDeploymentAdapter,
    ASCRDeploymentAdapter,
)
from neuroswarm_arm.evolution.interfaces.knowledge import KnowledgeView
from neuroswarm_arm.evolution.reflection.performix_rule_strategy import (
    PerformixAwareRuleStrategy,
)
from neuroswarm_arm.runtime.armcascade.interfaces.rl_agent import RLAction, StaticPolicyAgent
from neuroswarm_arm.runtime.armcascade.interfaces.types import ThresholdInputs
from neuroswarm_arm.runtime.dipa.aqr.quant_connector import AQRQuantConnector
from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest, WorkloadClass
from neuroswarm_arm.runtime.router.cost_router import CostRouter


def test_performix_low_ipc_draft_and_escalate():
    strat = PerformixAwareRuleStrategy()
    view = KnowledgeView(
        aggregate_metrics={
            "performix_available": 1.0,
            "ipc": 0.6,
            "draft_len": 8.0,
            "escalate_threshold": 0.4,
            "ascr_accept_rate": 0.7,
        }
    )
    analysis = strat.analyze(view)
    assert "performix_low_ipc" in analysis.findings
    reflection = strat.reflect(analysis)
    deltas = strat.propose(reflection)
    assert deltas
    params = deltas[0].parameters
    assert int(params["draft_len"]) == 6
    assert float(params["escalate_threshold"]) == pytest.approx(0.45)
    assert deltas[0].source == "performix_rule"


def test_performix_unavailable_no_performix_findings():
    strat = PerformixAwareRuleStrategy()
    view = KnowledgeView(
        aggregate_metrics={
            "performix_available": 0.0,
            "ipc": 0.1,  # present but gate fails — must not invent Performix findings
            "ascr_accept_rate": 0.9,
            "ascr_latency_ms": 100.0,
        }
    )
    analysis = strat.analyze(view)
    assert not any(f.startswith("performix_") for f in analysis.findings)
    deltas = strat.propose(strat.reflect(analysis))
    for d in deltas:
        assert d.source == "rule"
        assert "ipc=" not in (d.rationale or "")


def test_adapter_ascr_thresholds_change():
    from neuroswarm_arm.runtime.armcascade.engine import ASCREngine
    from neuroswarm_arm.runtime.armcascade.config.loader import load_ascr_config

    eng = ASCREngine(config=load_ascr_config(), registry=None, graphs={})
    adapter = ASCRDeploymentAdapter(target=eng, dry_run=False)
    adapter.apply(
        {
            "draft_len": 4,
            "accept_threshold": 0.82,
            "escalate_threshold": 0.5,
        }
    )
    assert isinstance(eng.thresholds.agent, StaticPolicyAgent)
    thr = eng.thresholds.compute(
        ThresholdInputs(
            historical_acceptance=0.9,
            cpu_utilization=0.2,
            entropy_estimate=0.2,
            complexity=0.2,
        )
    )
    assert thr.draft_len == 4
    assert thr.accept_threshold == pytest.approx(0.82)


def test_quant_preference_q4_sticks_fp8_rejected():
    aqr = AQRQuantConnector()
    assert aqr.set_arop_quant_preference("Q4_0") is True
    assert aqr._arop_quant_preference == "Q4_0"
    assert aqr.set_arop_quant_preference("FP8") is False
    assert aqr._arop_quant_preference == "Q4_0"

    req = InferenceRequest(messages=[{"role": "user", "content": "hi"}], agent_role="reasoning")
    q = aqr.choose(req, WorkloadClass.REASONING, constraints={})
    assert q == "Q4_0"

    adapter = AQRDeploymentAdapter(target=aqr, dry_run=False)
    aqr.clear_arop_quant_preference()
    adapter.apply({"quant_preference": "Q4_0"})
    assert aqr._arop_quant_preference == "Q4_0"
    adapter.apply({"quant_preference": "FP8"})
    # rejected — preference unchanged
    assert aqr._arop_quant_preference == "Q4_0"


def test_cost_router_tier_floor():
    CostRouter.clear_arop_tier_floor()
    router = CostRouter()
    # High-conf short query → tier 1 without floor
    d = router.route("hello world", tool_confidence=0.95)
    assert d.tier == 1

    CostRouter.set_arop_tier_floor(2)
    try:
        d2 = CostRouter().route("hello world", tool_confidence=0.95)
        assert d2.tier >= 2
        assert "arop_tier_floor=2" in d2.reason
    finally:
        CostRouter.clear_arop_tier_floor()

    adapter = AQRDeploymentAdapter(target=AQRQuantConnector(), dry_run=False)
    try:
        adapter.apply({"cascade_tier_bias": 3})
        d3 = CostRouter().route("hello world", tool_confidence=0.95)
        assert d3.tier == 3
    finally:
        CostRouter.clear_arop_tier_floor()


@pytest.mark.live
def test_axion_smoke_skipped_when_tiers_down():
    """Marker-only live smoke — skip when cascade tiers are unreachable."""
    import os
    import urllib.request

    base = os.getenv("NSA_LIVE_GATEWAY", "http://127.0.0.1:8080")
    try:
        with urllib.request.urlopen(f"{base}/ready", timeout=2) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception:
        pytest.skip("Axion/gateway not reachable")
    if "ready" not in body and '"status"' not in body:
        pytest.skip("gateway ready payload unavailable")
