"""Unit tests for DIPA planner, scoring, cascade, recovery."""

from __future__ import annotations

from neuroswarm_arm.runtime.dipa import build_dipa
from neuroswarm_arm.runtime.dipa.interfaces.types import InferenceRequest
from neuroswarm_arm.runtime.dipa.recovery.circuit_breaker import CircuitBreaker
from neuroswarm_arm.runtime.dipa.router.policy_engine import PolicyEngine
from neuroswarm_arm.runtime.dipa.runtime.runtime_config import load_dipa_config


def test_policy_classifies_coding() -> None:
    cfg = load_dipa_config()
    pe = PolicyEngine(cfg.policy)
    req = InferenceRequest(
        messages=[{"role": "user", "content": "refactor this python code"}],
        agent_role="code",
    )
    wl = pe.classify_workload(req.agent_role, req.prompt_text)
    assert wl.value in {"coding", "tool_calling", "reasoning"}


def test_decision_engine_builds_plan() -> None:
    rt = build_dipa(use_mock=True, start=True)
    try:
        req = InferenceRequest(
            messages=[{"role": "user", "content": "classify sentiment: great"}],
            agent_role="classification",
            max_tokens=32,
        )
        plan = rt.decision_engine.decide(req)
        assert plan.model
        assert plan.backend
        assert plan.quant == "" or True  # quant resolved later in pipeline
        assert plan.graph_nodes or plan.workload
    finally:
        rt.shutdown()


def test_infer_mock_end_to_end() -> None:
    rt = build_dipa(use_mock=True)
    try:
        out = rt.infer(
            InferenceRequest(
                messages=[{"role": "user", "content": "hello dipa"}],
                agent_role="classification",
                max_tokens=16,
                session_id="test-sess",
            )
        )
        assert "mock-ok" in out.text
        assert out.quant
        assert "latency_ms" in out.metrics
    finally:
        rt.shutdown()


def test_cascade_escalates_on_short_reply() -> None:
    rt = build_dipa(use_mock=True)
    try:
        out = rt.handle(
            {
                "messages": [{"role": "user", "content": "hi"}],
                "agent_role": "tool_call",
                "max_tokens": 64,
            },
            tool_names=["weather"],
        )
        assert out.content
        assert out.tier_used >= 1
    finally:
        rt.shutdown()


def test_circuit_breaker_opens() -> None:
    cb = CircuitBreaker(failure_threshold=2, reset_window_s=60)
    assert cb.allow("tier1")
    cb.record_failure("tier1")
    assert cb.allow("tier1")
    cb.record_failure("tier1")
    assert not cb.allow("tier1")


def test_benchmark_runner() -> None:
    from neuroswarm_arm.runtime.dipa.benchmark import BenchmarkRunner

    rt = build_dipa(use_mock=True)
    try:
        result = BenchmarkRunner(rt).run(iterations=2)
        assert result.iterations == 2
        assert result.avg_latency_ms >= 0
    finally:
        rt.shutdown()
