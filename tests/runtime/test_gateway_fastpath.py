"""Gateway HAOE fast-path unit tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from neuroswarm_arm.gateway import AgentGateway
from neuroswarm_arm.schemas import ChatRequest, ChatResponse, Message


def _routed(*, high_confidence: bool, tools: bool = False) -> SimpleNamespace:
    if tools:
        return SimpleNamespace(
            tool_names=["S3 Put Object"],
            tool_ids=["s3.put_object"],
            schemas=[{"name": "s3.put_object"}],
            confidence_top1=0.85,
            high_confidence=high_confidence,
        )
    return SimpleNamespace(
        tool_names=[],
        tool_ids=[],
        schemas=[],
        confidence_top1=0.2,
        high_confidence=high_confidence,
    )


def test_fast_path_skips_haoe_on_high_confidence():
    haoe = MagicMock()
    cascade = MagicMock()
    cascade.handle.return_value = ChatResponse(
        id="r1",
        content="ok",
        model="m",
        tier_used=1,
        thinking_token_cap=256,
        metrics={},
    )
    router = MagicMock()
    router.route_result.return_value = _routed(high_confidence=True, tools=True)
    router.prompt_block.return_value = ""
    router.config = SimpleNamespace(high_conf_thinking_budget=256)

    gw = AgentGateway(
        registry=MagicMock(),
        semantic_router=router,
        cascade=cascade,
        haoe=haoe,
        acr=None,
    )
    req = ChatRequest(messages=[Message(role="user", content="upload to s3")])
    out = gw._handle_chat_body(req)

    haoe.submit_workflow.assert_not_called()
    cascade.handle.assert_called_once()
    assert out.metrics.get("haoe_bypassed") in (True, 1, 1.0)


def test_low_confidence_uses_haoe():
    haoe = MagicMock()
    haoe.submit_workflow.return_value = SimpleNamespace(
        output=ChatResponse(
            id="r2",
            content="via-haoe",
            model="m",
            tier_used=1,
            thinking_token_cap=256,
            metrics={},
        )
    )
    cascade = MagicMock()
    router = MagicMock()
    router.route_result.return_value = _routed(high_confidence=False, tools=True)

    gw = AgentGateway(
        registry=MagicMock(),
        semantic_router=router,
        cascade=cascade,
        haoe=haoe,
        acr=None,
    )
    req = ChatRequest(messages=[Message(role="user", content="maybe tools")])
    out = gw._handle_chat_body(req)

    haoe.submit_workflow.assert_called_once()
    cascade.handle.assert_not_called()
    assert out.content == "via-haoe"


def test_acr_blocks_fast_path():
    haoe = MagicMock()
    haoe.submit_workflow.return_value = SimpleNamespace(
        output=ChatResponse(
            id="r3",
            content="acr",
            model="m",
            tier_used=1,
            thinking_token_cap=256,
            metrics={},
        )
    )
    cascade = MagicMock()
    router = MagicMock()
    router.route_result.return_value = _routed(high_confidence=True, tools=False)

    gw = AgentGateway(
        registry=MagicMock(),
        semantic_router=router,
        cascade=cascade,
        haoe=haoe,
        acr=MagicMock(),
    )
    req = ChatRequest(messages=[Message(role="user", content="hi")])
    gw._handle_chat_body(req)

    haoe.submit_workflow.assert_called_once()
    cascade.handle.assert_not_called()
