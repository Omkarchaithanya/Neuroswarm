"""End-to-end: SpeculativeEngine hooked into AgentGateway + /metrics."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from neuroswarm_arm.gateway import AgentGateway
from neuroswarm_arm.metrics.compat import MetricsStore
from neuroswarm_arm.runtime.dipa.speculative.engine import SpeculativeEngine
from neuroswarm_arm.runtime.dipa.speculative.executor import SpeculativeExecutor
from neuroswarm_arm.runtime.dipa.speculative.predictor import ToolPrediction
from neuroswarm_arm.runtime.dipa.speculative.tool_cache import ToolOutputCache
from neuroswarm_arm.schemas import ChatRequest, ChatResponse, Message


class FakePredictor:
    def __init__(self, preds: list[ToolPrediction]) -> None:
        self.preds = list(preds)

    async def predict(self, messages: list[dict]) -> list[ToolPrediction]:
        del messages
        await asyncio.sleep(0.01)
        return list(self.preds)


class FakeCascade:
    def __init__(self, *, tool_name: str, tool_args: dict[str, Any], delay_s: float = 0.08) -> None:
        self.tool_name = tool_name
        self.tool_args = dict(tool_args)
        self.delay_s = delay_s

    async def generate(self, request: ChatRequest) -> ChatResponse:
        del request
        await asyncio.sleep(self.delay_s)
        return ChatResponse(
            model="cascade",
            tier_used=2,
            content="cascade-pending",
            thinking_token_cap=256,
            tool_calls=[
                {
                    "type": "function",
                    "function": {
                        "name": self.tool_name,
                        "arguments": self.tool_args,
                    },
                }
            ],
            metrics={},
        )


class FakeMCP:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, tool_name: str, args: dict[str, Any], **kwargs: Any) -> Any:
        del kwargs
        self.calls.append((tool_name, dict(args)))
        await asyncio.sleep(0.02)
        return {"ok": True, "result": f"mcp:{tool_name}"}


def _routed_with_schemas() -> SimpleNamespace:
    return SimpleNamespace(
        tool_names=["echo"],
        tool_ids=["echo"],
        schemas=[{"type": "function", "function": {"name": "echo"}}],
        confidence_top1=0.9,
        high_confidence=True,
    )


@pytest.fixture
def metrics_store() -> MetricsStore:
    return MetricsStore()


@pytest.fixture
def wired_app(monkeypatch: pytest.MonkeyPatch, metrics_store: MetricsStore) -> FastAPI:
    monkeypatch.setenv("NSA_TOOL_SPEC_ENABLED", "1")

    cache = ToolOutputCache(max_size=64, ttl_seconds=300)
    mcp = FakeMCP()
    executor = SpeculativeExecutor(
        mcp_manager=mcp,
        cache=cache,
        inflight_sem=asyncio.Semaphore(4),
        tool_timeout_s=2.0,
    )
    pred = ToolPrediction(tool_name="echo", args={"q": "hi"}, confidence=0.95)
    engine = SpeculativeEngine(
        predictor=FakePredictor([pred]),
        executor=executor,
        cascade=FakeCascade(tool_name="echo", tool_args={"q": "hi"}),
        cache=cache,
        metrics=metrics_store,
    )

    router = MagicMock()
    router.route_result.return_value = _routed_with_schemas()
    router.prompt_block.return_value = ""
    router.config = SimpleNamespace(high_conf_thinking_budget=256)

    gateway = AgentGateway(
        registry=MagicMock(),
        semantic_router=router,
        cascade=MagicMock(),
        haoe=MagicMock(),
        acr=None,
        speculative_engine=engine,
    )

    app = FastAPI()
    app.state.tool_cache = cache
    app.state.speculative_engine = engine
    app.state.metrics_store = metrics_store

    @app.post("/v1/chat/completions")
    async def chat(req: ChatRequest):
        return gateway.handle_chat(req).model_dump()

    @app.get("/metrics")
    def export_metrics():
        return metrics_store.export_prometheus()

    @app.get("/v1/tools/cache")
    async def tools_cache():
        return cache.snapshot()

    @app.get("/v1/tools/spec_debug")
    def spec_debug(reset: int = 0):
        events = engine.debug_snapshot(reset=bool(reset))
        return {"events": events, "count": len(events)}

    return app


def test_chat_speculative_hit_reports_metadata_and_metrics(wired_app: FastAPI) -> None:
    client = TestClient(wired_app)
    res = client.post(
        "/v1/chat/completions",
        json={
            "model": "cascade",
            "messages": [{"role": "user", "content": "please echo hi"}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("speculative_hit") is True or body.get("metrics", {}).get("cache_hit") in (
        1,
        1.0,
        True,
    )
    assert "cache_hit" in body.get("metrics", {}) or body.get("speculative_hit") is True

    metrics_txt = client.get("/metrics").text
    assert "neuroswarm_tool_spec_hit_total" in metrics_txt
    assert "neuroswarm_tool_spec_miss_total" in metrics_txt
    assert "neuroswarm_tool_spec_time_saved_ms_total" in metrics_txt
    assert "neuroswarm_tool_spec_inflight" in metrics_txt

    dbg = client.get("/v1/tools/spec_debug").json()
    assert dbg["count"] >= 1
    assert any(e.get("event") == "hit" for e in dbg["events"])


def test_disabled_flag_falls_through_to_haoe(monkeypatch: pytest.MonkeyPatch) -> None:
    """NSA_TOOL_SPEC_ENABLED unset/0 → engine ignored → HAOE path (byte-identical gate)."""
    monkeypatch.delenv("NSA_TOOL_SPEC_ENABLED", raising=False)

    haoe = MagicMock()
    haoe.submit_workflow.return_value = SimpleNamespace(
        output=ChatResponse(
            model="m",
            tier_used=1,
            content="via-haoe",
            thinking_token_cap=256,
            metrics={},
        )
    )
    engine = MagicMock()
    router = MagicMock()
    # Low confidence → HAOE path (not cascade fast-path).
    router.route_result.return_value = SimpleNamespace(
        tool_names=["echo"],
        schemas=[{"name": "echo"}],
        confidence_top1=0.2,
        high_confidence=False,
    )

    gw = AgentGateway(
        registry=MagicMock(),
        semantic_router=router,
        cascade=MagicMock(),
        haoe=haoe,
        acr=None,
        speculative_engine=engine,
    )
    req = ChatRequest(messages=[Message(role="user", content="upload")])
    out = gw.handle_chat(req)
    engine.generate.assert_not_called()
    haoe.submit_workflow.assert_called_once()
    assert out.content == "via-haoe"


def test_engine_none_is_legacy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_TOOL_SPEC_ENABLED", "1")
    haoe = MagicMock()
    haoe.submit_workflow.return_value = SimpleNamespace(
        output=ChatResponse(
            model="m",
            tier_used=1,
            content="legacy",
            thinking_token_cap=256,
            metrics={},
        )
    )
    router = MagicMock()
    router.route_result.return_value = SimpleNamespace(
        tool_names=["echo"],
        schemas=[{"name": "echo"}],
        confidence_top1=0.2,
        high_confidence=False,
    )
    gw = AgentGateway(
        registry=MagicMock(),
        semantic_router=router,
        cascade=MagicMock(),
        haoe=haoe,
        acr=None,
        speculative_engine=None,
    )
    out = gw.handle_chat(ChatRequest(messages=[Message(role="user", content="x")]))
    haoe.submit_workflow.assert_called_once()
    assert out.content == "legacy"
