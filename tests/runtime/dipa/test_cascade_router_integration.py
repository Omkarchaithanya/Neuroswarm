"""CascadeRouter.handle passes router_result into governor.cap."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from neuroswarm_arm.governor import ReasoningGovernor
from neuroswarm_arm.inference.cascade import CascadeRouter
from neuroswarm_arm.schemas import ChatRequest, Message, PlanState


class _Client:
    def chat(self, *args, **kwargs):
        return {
            "choices": [{"message": {"content": "done with certainty"}}],
            "content": "done with certainty",
        }


def test_cascade_router_passes_router_result_to_governor_cap() -> None:
    gov = MagicMock(spec=ReasoningGovernor)
    gov.cap.return_value = 256
    gov.prompt.return_value = "think"

    router = CascadeRouter(
        tier1=_Client(),
        tier2=_Client(),
        tier3=_Client(),
        governor=gov,
        dipa=None,
    )
    req = ChatRequest(messages=[Message(role="user", content="hi")], model="cascade")
    rr = SimpleNamespace(confidence_top1=0.95, tools=[], tool_ids=[], tool_names=[])
    router.handle(req, ["t1"], router_result=rr, tool_confidence=0.4)
    assert gov.cap.called
    _, kwargs = gov.cap.call_args
    # keyword form from cascade.py
    assert kwargs.get("router_result") is rr


def test_governor_cap_maxes_confidence() -> None:
    gov = ReasoningGovernor(rtg=None)
    plan = PlanState(tool_confidence_top1=0.4)
    rr = SimpleNamespace(confidence_top1=0.9)
    cap = gov.cap(plan, router_result=rr)
    assert cap <= 256
    plan2 = PlanState(tool_confidence_top1=0.95)
    rr2 = SimpleNamespace(confidence_top1=0.1)
    assert gov.cap(plan2, router_result=rr2) <= 256
