"""HAOE tool_search_activation step: bridge vs pass_through."""

from __future__ import annotations

import os
from types import SimpleNamespace

from neuroswarm_arm.runtime.haoe.execution.execution_context import ExecutionContext
from neuroswarm_arm.runtime.haoe.integration.chat import build_chat_handlers
from neuroswarm_arm.runtime.haoe.interfaces.types import CorrelationIds
from neuroswarm_arm.runtime.router.models import RoutingResult, ScoredTool, ToolRecord
from neuroswarm_arm.runtime.router.registry import ToolRegistry
from neuroswarm_arm.runtime.router.tool_search import BRIDGE_TOOL_SCHEMA


class _FakeRouter:
    def __init__(self) -> None:
        self.registry = ToolRegistry()
        for i in range(30):
            self.registry.register(
                ToolRecord(
                    id=f"aws.tool_{i}",
                    name=f"tool_{i}",
                    description="x" * 400,
                    namespace="aws",
                    input_schema={"type": "object", "properties": {"a": {"type": "string"}}},
                )
            )

    def route(self, query: str, *args, **kwargs):
        tool = self.registry.get("aws.tool_0")
        scored = ScoredTool(
            tool=tool,
            score=0.9,
            confidence=0.9,
            schema={
                "type": "function",
                "function": {"name": tool.name, "description": tool.description, "parameters": {}},
            },
        )
        return RoutingResult(tools=[scored], top_k=1, confidence_top1=0.9, query=query)


class _FakeCascade:
    def handle(self, req, tool_names=None, **kwargs):
        return SimpleNamespace(content="ok", metrics={})


def _handlers():
    req = SimpleNamespace(
        messages=[SimpleNamespace(content="do stuff", role="user")],
        session_id="s1",
        agent_id="a1",
        agent_role="tool_call",
    )
    return build_chat_handlers(
        semantic_router=_FakeRouter(),
        cascade=_FakeCascade(),
        kv_runtime=None,
        request=req,
    )


def test_bridge_mode_replaces_tool_schemas(monkeypatch) -> None:
    monkeypatch.setenv("TOOL_SEARCH_ENABLED", "on")
    handlers = _handlers()
    ctx = ExecutionContext(ids=CorrelationIds())
    handlers["semantic_route"](ctx)
    before = list(ctx.baggage.get("tool_schemas") or [])
    assert before  # routed schemas present
    mode = handlers["tool_search_activation"](ctx)
    assert mode == "bridge"
    assert ctx.baggage["tool_schemas"] == [BRIDGE_TOOL_SCHEMA]
    assert "<tool_listing>" in (ctx.baggage.get("tool_prompt_block") or "")


def test_pass_through_leaves_schemas(monkeypatch) -> None:
    monkeypatch.setenv("TOOL_SEARCH_ENABLED", "off")
    handlers = _handlers()
    ctx = ExecutionContext(ids=CorrelationIds())
    handlers["semantic_route"](ctx)
    snap = list(ctx.baggage.get("tool_schemas") or [])
    prompt = ctx.baggage.get("tool_prompt_block")
    mode = handlers["tool_search_activation"](ctx)
    assert mode == "pass_through"
    assert ctx.baggage["tool_schemas"] == snap
    assert ctx.baggage.get("tool_prompt_block") == prompt
