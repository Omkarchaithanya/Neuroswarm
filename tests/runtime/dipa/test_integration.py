"""Integration: DIPA lifecycle with HAOE chat handler protocol."""

from __future__ import annotations

from neuroswarm_arm.runtime.dipa import build_dipa
from neuroswarm_arm.runtime.haoe.integration.chat import build_chat_handlers
from neuroswarm_arm.schemas import ChatRequest, Message


class _FakeRouter:
    def route(self, query: str):
        return []


def test_haoe_handlers_call_dipa() -> None:
    dipa = build_dipa(use_mock=True)
    try:
        req = ChatRequest(
            messages=[Message(role="user", content="ping")],
            agent_role="classification",
            max_tokens=16,
        )
        handlers = build_chat_handlers(
            semantic_router=_FakeRouter(),
            inference=dipa,
            kv_runtime=None,
            request=req,
        )
        # Exercise cascade node directly with a minimal context stand-in.
        from neuroswarm_arm.runtime.haoe.execution.execution_context import (
            ExecutionContext,
        )
        from neuroswarm_arm.runtime.haoe.interfaces.types import CorrelationIds

        ctx = ExecutionContext(
            ids=CorrelationIds(request_id="r1"),
        )
        handlers["semantic_route"](ctx)
        resp = handlers["cascade"](ctx)
        assert resp.content
        assert handlers["response"](ctx) is resp
    finally:
        dipa.shutdown()
