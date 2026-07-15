"""ROF unit tests — context, sampling, schemas."""

from __future__ import annotations

import pytest

from neuroswarm_arm.armora.telemetry.context import (
    RuntimeTraceContext,
    clear_current_context,
    get_current_context,
    set_current_context,
)
from neuroswarm_arm.armora.telemetry.sampling import (
    AdaptiveSampler,
    AlwaysOffSampler,
    AlwaysOnSampler,
    HeadRatioSampler,
    TailSampler,
    build_sampler,
)
from neuroswarm_arm.armora.telemetry.config import ROFRuntimeConfig
from neuroswarm_arm.armora.telemetry.schemas import AttributeKeys, EventType, SpanNames


def test_context_immutable_evolve() -> None:
    ctx = RuntimeTraceContext(request_id="r1", agent_id="a1")
    child = ctx.evolve(agent_id="a2")
    assert ctx.agent_id == "a1"
    assert child.agent_id == "a2"
    assert child.request_id == "r1"
    with pytest.raises(Exception):
        ctx.agent_id = "x"  # type: ignore[misc]


def test_context_child_span_parent() -> None:
    ctx = RuntimeTraceContext()
    child = ctx.child_span(backend_id="llama.cpp")
    assert child.parent_span_id == ctx.span_id
    assert child.span_id != ctx.span_id
    assert child.trace_id == ctx.trace_id
    assert child.backend_id == "llama.cpp"


def test_contextvars_roundtrip() -> None:
    clear_current_context()
    ctx = RuntimeTraceContext(request_id="abc")
    token = set_current_context(ctx)
    assert get_current_context() is not None
    assert get_current_context().request_id == "abc"
    from neuroswarm_arm.armora.telemetry.context import reset_current_context

    reset_current_context(token)
    clear_current_context()


def test_carrier_roundtrip() -> None:
    ctx = RuntimeTraceContext(request_id="r", envelope_id="e", numa_node=1)
    carrier = ctx.to_carrier()
    restored = RuntimeTraceContext.from_carrier(carrier)
    assert restored.request_id == "r"
    assert restored.envelope_id == "e"
    assert restored.numa_node == 1


def test_haoe_correlation_bridge() -> None:
    from neuroswarm_arm.runtime.haoe.interfaces.types import CorrelationIds

    ids = CorrelationIds(agent_id="agent-x")
    ctx = RuntimeTraceContext.from_haoe_correlation(ids)
    back = ctx.to_haoe_correlation()
    assert back.trace_id == ctx.trace_id
    assert back.agent_id == "agent-x"


def test_samplers() -> None:
    assert AlwaysOnSampler().should_sample(name="x").sampled is True
    assert AlwaysOffSampler().should_sample(name="x").sampled is False
    forced = AlwaysOffSampler().should_sample(
        name="x", attributes={AttributeKeys.FORCE_SAMPLE: True}
    )
    assert forced.sampled is True and forced.force is True
    head = HeadRatioSampler(1.0)
    assert head.should_sample(name="x").sampled is True
    head0 = HeadRatioSampler(0.0)
    assert head0.should_sample(name="x").sampled is False
    tail = TailSampler(100.0)
    assert tail.finalize(latency_ms=200.0).sampled is True
    assert tail.finalize(latency_ms=1.0, error=False).sampled is False
    adaptive = AdaptiveSampler(base_ratio=0.0)
    adaptive.record_outcome(error=True, latency_ms=5000)
    # after errors, ratio rises — may still be random; just ensure API works
    decision = adaptive.should_sample(name="x")
    assert isinstance(decision.sampled, bool)


def test_build_sampler_from_config() -> None:
    cfg = ROFRuntimeConfig(sampler="head", head_ratio=1.0)
    s = build_sampler(cfg)
    assert s.should_sample(name="n").sampled is True


def test_span_and_event_names_stable() -> None:
    assert SpanNames.REQUEST.startswith("nexus.")
    assert EventType.COST_REPORT_GENERATED.value == "CostReportGenerated"
