"""Mem0 recall query bias from router_result."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from neuroswarm_arm.runtime.haoe.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.haoe.integration.chat import build_chat_handlers
from neuroswarm_arm.runtime.haoe.interfaces.types import CorrelationIds
from neuroswarm_arm.runtime.router.models import RoutingResult, ScoredTool, ToolRecord


def test_mem0_recall_biases_query_when_router_result_present() -> None:
    neuro = MagicMock()
    neuro.recall.return_value = ["fact-a"]
    neuro.remember_success = MagicMock()

    req = SimpleNamespace(
        messages=[SimpleNamespace(content="upload file", role="user")],
        session_id="s1",
        agent_id="agent-1",
        agent_role="tool_call",
    )
    handlers = build_chat_handlers(
        semantic_router=SimpleNamespace(route=lambda *a, **k: []),
        cascade=SimpleNamespace(handle=lambda *a, **k: SimpleNamespace(content="ok")),
        kv_runtime=None,
        request=req,
        memory=neuro,
    )
    ctx = ExecutionContext(ids=CorrelationIds(agent_id="agent-1"))
    tool = ToolRecord(id="aws.s3", name="s3_presign_url", description="presign")
    ctx.baggage["router_result"] = RoutingResult(
        tools=[ScoredTool(tool=tool, score=0.9, confidence=0.9)],
        confidence_top1=0.9,
    )
    facts = handlers["mem0_recall"](ctx)
    assert "fact-a" in facts
    # Last non-reflection recall should include tool name bias.
    calls = [c.args for c in neuro.recall.call_args_list]
    assert any("s3_presign_url" in str(c) for c in calls)
