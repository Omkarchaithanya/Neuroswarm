"""HAOE chat semantic_route stashes RoutingResult in baggage."""

from __future__ import annotations

from types import SimpleNamespace

from neuroswarm_arm.runtime.haoe.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.haoe.integration.chat import build_chat_handlers
from neuroswarm_arm.runtime.haoe.interfaces.types import CorrelationIds
from neuroswarm_arm.runtime.router.models import RoutingResult, ScoredTool, ToolRecord


class _FakeRouter:
    def route(self, query: str, *args, **kwargs):
        tool = ToolRecord(id="aws.s3", name="s3_presign_url", description="presign")
        scored = ScoredTool(tool=tool, score=0.9, confidence=0.9, schema={
            "type": "function",
            "function": {"name": "s3_presign_url", "description": "presign", "parameters": {}},
        })
        return RoutingResult(
            tools=[scored],
            top_k=3,
            confidence_top1=0.9,
            high_confidence=True,
            query=query,
        )


class _FakeCascade:
    def handle(self, req, tool_names=None, **kwargs):
        return SimpleNamespace(content="ok", metrics={})


def test_semantic_route_stashes_routing_result_object() -> None:
    req = SimpleNamespace(
        messages=[SimpleNamespace(content="presign an s3 url", role="user")],
        session_id="s1",
        agent_id="a1",
        agent_role="tool_call",
    )
    handlers = build_chat_handlers(
        semantic_router=_FakeRouter(),
        cascade=_FakeCascade(),
        kv_runtime=None,
        request=req,
    )
    ctx = ExecutionContext(ids=CorrelationIds(agent_id="a1"))
    names = handlers["semantic_route"](ctx)
    assert "s3_presign_url" in names
    rr = ctx.baggage.get("router_result")
    assert rr is not None
    assert isinstance(rr, RoutingResult)
    assert rr.confidence_top1 == 0.9
    assert rr.tools[0].name == "s3_presign_url"
