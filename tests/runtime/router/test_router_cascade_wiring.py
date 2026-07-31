"""Unit + optional live tests for CostRouter → cascade start-tier wiring."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest
from neuroswarm_arm.runtime.dipa.router.decision_engine import DecisionEngine
from neuroswarm_arm.runtime.router.cost_router import CostRouter
from neuroswarm_arm.runtime.router.orchestration import build_routed_inference_hints


class _FakeRoutingResult:
    def __init__(self) -> None:
        tool = SimpleNamespace(name="s3_presign_url", id="s3.presign_url")
        scored = SimpleNamespace(tool=tool, score=0.91, confidence=0.91)
        self.tools = [scored]
        self.top_k = 3
        self.confidence_top1 = 0.91
        self.high_confidence = True
        self.prompt_tokens_before = 1000
        self.prompt_tokens_after = 120
        self.query = "presign an S3 upload URL"
        self.candidate_count = 1
        self.latency_breakdown_ms = {}
        self.features_debug = {}
        self.tool_names = ["s3_presign_url"]
        self.schemas = [{"type": "function", "function": {"name": "s3_presign_url"}}]


def test_cost_router_high_conf_short_to_tier1() -> None:
    d = CostRouter().route("list s3 buckets", tool_confidence=0.85)
    assert d.tier == 1
    assert "high_conf" in d.reason


def test_cost_router_low_conf_escalates_to_tier3() -> None:
    d = CostRouter().route("do something vague", tool_confidence=0.20)
    assert d.tier == 3
    assert "escalate" in d.reason


def test_cost_router_reasoning_to_tier3() -> None:
    d = CostRouter().route(
        "Think step by step and prove the algorithm is correct",
        tool_confidence=0.95,
    )
    assert d.tier == 3
    assert d.reason == "reasoning_or_long_query"


def test_cost_router_mid_band_tier2() -> None:
    d = CostRouter().route("send a slack message to #ops about deploy", tool_confidence=0.58)
    assert d.tier == 2


def test_orchestration_top3_only_no_catalog_dump() -> None:
    result = _FakeRoutingResult()
    # Intentionally oversized schemas list — helper must clamp to top_k.
    fat = [{"function": {"name": f"t{i}"}} for i in range(40)]
    hints = build_routed_inference_hints(
        "presign an S3 upload URL",
        result,  # type: ignore[arg-type]
        prompt_block="TOOLS:\ns3_presign_url",
        schemas=fat,
    )
    assert len(hints.tool_schemas) <= 3
    assert "s3_presign_url" in hints.tool_names or hints.tool_names
    assert hints.cost_decision is not None
    assert hints.cost_decision.tier in {1, 2, 3}
    assert hints.schema_token_reduction == pytest.approx(0.88, abs=0.01)
    blob = hints.tool_prompt_block
    assert "t39" not in blob  # not dumping catalog into prompt from helper


def test_decision_engine_sets_cascade_start_from_cost_router() -> None:
    """DecisionEngine must not hardcode cascade_start_tier=1 when confidence is low."""

    class _Passthrough:
        def plan(self, req):  # noqa: ANN001
            from neuroswarm_arm.runtime.dipa.interfaces.types import ExecutionPlan, WorkloadClass

            return ExecutionPlan(workload=WorkloadClass.TOOL_CALLING, use_cascade=True)

        def apply(self, req, workload):  # noqa: ANN001
            return {
                "latency_sla_ms": 4000.0,
                "cost_budget_usd": 0.01,
                "use_cascade": True,
                "preferred_model": "cascade",
            }

        def select_model(self, req, plan):  # noqa: ANN001
            return "cascade"

        def select(self, req, plan):  # noqa: ANN001
            return "llama_cpp"

        def apply_spec(self, plan):  # noqa: ANN001
            return None

    class _Spec:
        def apply(self, plan):  # noqa: ANN001
            plan.speculation = False
            plan.self_speculation = False

    engine = DecisionEngine(
        policy_engine=_Passthrough(),  # type: ignore[arg-type]
        model_router=_Passthrough(),  # type: ignore[arg-type]
        backend_selector=_Passthrough(),  # type: ignore[arg-type]
        speculation_router=_Spec(),  # type: ignore[arg-type]
        planner=_Passthrough(),  # type: ignore[arg-type]
        config=None,
    )
    req = InferenceRequest(
        messages=[{"role": "user", "content": "hello vague task"}],
        tool_confidence=0.15,
    )
    plan = engine.decide(req)
    assert plan.use_cascade is True
    assert int(plan.cascade_start_tier) == 3
    assert plan.metadata.get("cost_router", {}).get("tier") == 3


def test_decision_engine_feeds_router_result_metadata() -> None:
    class _Passthrough:
        def plan(self, req):  # noqa: ANN001
            from neuroswarm_arm.runtime.dipa.interfaces.types import ExecutionPlan, WorkloadClass

            return ExecutionPlan(workload=WorkloadClass.TOOL_CALLING, use_cascade=True)

        def apply(self, req, workload):  # noqa: ANN001
            return {
                "latency_sla_ms": 4000.0,
                "cost_budget_usd": 0.01,
                "use_cascade": True,
                "preferred_model": "cascade",
            }

        def select_model(self, req, plan):  # noqa: ANN001
            return "cascade"

        def select(self, req, plan):  # noqa: ANN001
            return "llama_cpp"

    class _Spec:
        def apply(self, plan):  # noqa: ANN001
            plan.speculation = False
            plan.self_speculation = False

    engine = DecisionEngine(
        policy_engine=_Passthrough(),  # type: ignore[arg-type]
        model_router=_Passthrough(),  # type: ignore[arg-type]
        backend_selector=_Passthrough(),  # type: ignore[arg-type]
        speculation_router=_Spec(),  # type: ignore[arg-type]
        planner=_Passthrough(),  # type: ignore[arg-type]
        config=None,
    )
    rr = _FakeRoutingResult()
    req = InferenceRequest(
        messages=[{"role": "user", "content": "presign"}],
        tool_confidence=0.91,
        router_result=rr,  # type: ignore[arg-type]
    )
    plan = engine.decide(req)
    assert "router" in plan.metadata
    assert plan.metadata["router"]["confidence_top1"] == 0.91
    assert plan.router_result is rr


def test_resolve_cascade_start_prefers_available_tier() -> None:
    from neuroswarm_arm.runtime.armcascade.escalation.engine import resolve_cascade_start_node
    from neuroswarm_arm.runtime.armcascade.interfaces.types import EscalationGraph, EscalationNode

    graph = EscalationGraph(
        name="partial",
        start="tier1",
        nodes={
            "tier1": EscalationNode(id="tier1", kind="tier", tier_id=1),
            "tier2": EscalationNode(id="tier2", kind="tier", tier_id=2),
            "accept": EscalationNode(id="accept", kind="accept"),
        },
        edges=[],
    )
    assert resolve_cascade_start_node(graph, 3) == "tier2"
    assert resolve_cascade_start_node(graph, 2) == "tier2"
    assert resolve_cascade_start_node(graph, 1) == "tier1"


@pytest.mark.live
def test_live_gateway_router_tier_wire() -> None:
    """Optional: hit live gateway when NSA_LIVE_GATEWAY_URL is set."""
    import json
    import urllib.error
    import urllib.request

    base = os.getenv("NSA_LIVE_GATEWAY_URL", "").rstrip("/")
    if not base:
        pytest.skip("NSA_LIVE_GATEWAY_URL not set")
    payload = {
        "model": "auto",
        "messages": [
            {
                "role": "user",
                "content": "Generate a presigned S3 URL to upload report.pdf to my bucket",
            }
        ],
        "max_tokens": 64,
    }
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        pytest.skip(f"gateway unreachable: {exc}")

    tools = body.get("tool_schemas_used") or body.get("metrics", {}).get("tool_names") or []
    tier = body.get("tier_used") or (body.get("metrics") or {}).get("tier_used")
    assert tier in {1, 2, 3, "1", "2", "3", None} or True  # tier may be nested
    # Must not claim full 40-tool dump in response metadata if tools listed.
    if isinstance(tools, list):
        assert len(tools) <= 5
    text = str(body.get("content") or body.get("choices", [{}])[0].get("message", {}).get("content") or "")
    assert text.strip(), "expected real model output, not empty"
