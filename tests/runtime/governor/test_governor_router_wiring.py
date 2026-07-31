"""ReasoningGovernor.cap(plan, router_result=...) wiring."""

from __future__ import annotations

from types import SimpleNamespace

from neuroswarm_arm.governor import ReasoningGovernor
from neuroswarm_arm.schemas import PlanState


def test_cap_patches_tool_confidence_with_max() -> None:
    gov = ReasoningGovernor(rtg=None)
    plan = PlanState(tool_confidence_top1=0.3, kv_pressure=0.0, memory_pressure=0.0)
    rr = SimpleNamespace(confidence_top1=0.92)
    cap = gov.cap(plan, router_result=rr)
    # High confidence path → small legacy cap
    assert cap == 256


def test_cap_keeps_higher_upstream_confidence() -> None:
    gov = ReasoningGovernor(rtg=None)
    plan = PlanState(tool_confidence_top1=0.95)
    rr = SimpleNamespace(confidence_top1=0.2)
    cap = gov.cap(plan, router_result=rr)
    assert cap == 256  # upstream 0.95 still wins via max


def test_cap_without_router_result_unchanged() -> None:
    gov = ReasoningGovernor(rtg=None)
    plan = PlanState(tool_confidence_top1=0.0)
    a = gov.cap(plan)
    b = gov.cap(plan, router_result=None)
    assert a == b
