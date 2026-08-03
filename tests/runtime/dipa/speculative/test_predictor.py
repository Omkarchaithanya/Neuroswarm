"""Unit tests for ToolCallPredictor (FakeDraftClient — no llama-server)."""

from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from neuroswarm_arm.runtime.dipa.speculative.predictor import ToolCallPredictor
from neuroswarm_arm.runtime.router.models import RoutingResult, ScoredTool, ToolRecord
from neuroswarm_arm.schemas import ToolDef
from neuroswarm_arm.tools.registry import ToolRegistry


def _schema(name: str, tool_id: str | None = None) -> dict[str, Any]:
    tid = tool_id or name
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"tool {name}",
            "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
        },
        "id": tid,
    }


def _tool_record(i: int) -> ToolRecord:
    name = f"tool_{i}"
    return ToolRecord(
        id=name,
        name=name,
        description=f"description for {name}",
        params={"q": "query"},
    )


def _registry(n: int = 46) -> ToolRegistry:
    reg = ToolRegistry()
    for i in range(n):
        t = _tool_record(i)
        reg.register(
            ToolDef(
                id=t.id,
                name=t.name,
                description=t.description,
                params=dict(t.params),
            )
        )
    return reg


def _scored(name: str, score: float = 0.9) -> ScoredTool:
    rec = ToolRecord(id=name, name=name, description=f"desc {name}", params={"q": "query"})
    return ScoredTool(tool=rec, score=score, schema=_schema(name))


class FakeDraftClient:
    """Canned llama.cpp chat/completions stand-in (sync or async)."""

    def __init__(
        self,
        *,
        content: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        confidence: float | None = None,
        logprob: float | None = None,
        sleep_s: float = 0.0,
        garbage: bool = False,
        use_async: bool = True,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls
        self.confidence = confidence
        self.logprob = logprob
        self.sleep_s = sleep_s
        self.garbage = garbage
        self.use_async = use_async
        self.last_messages: list[dict] | None = None
        self.last_kwargs: dict[str, Any] = {}
        self.calls = 0

    def _payload(self) -> dict[str, Any]:
        if self.garbage:
            return {
                "choices": [{"message": {"content": "not a tool call at all!!!"}}],
            }
        msg: dict[str, Any] = {}
        if self.tool_calls is not None:
            msg["tool_calls"] = self.tool_calls
            msg["content"] = self.content or ""
        else:
            msg["content"] = self.content or json.dumps(
                {"name": "search", "arguments": {"q": "arm"}}
            )
        choice: dict[str, Any] = {"message": msg}
        if self.logprob is not None:
            choice["logprobs"] = {
                "content": [
                    {"token": "x", "logprob": float(self.logprob), "top_logprobs": []}
                    for _ in range(4)
                ]
            }
        out: dict[str, Any] = {"choices": [choice]}
        if self.confidence is not None:
            out["confidence"] = float(self.confidence)
        return out

    async def generate_with_logits(self, messages: list[dict], **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        self.last_messages = messages
        self.last_kwargs = dict(kwargs)
        if self.sleep_s > 0:
            await asyncio.sleep(self.sleep_s)
        return self._payload()


class FakeSemanticRouter:
    def __init__(self, top_names: list[str], *, top_k: int = 3) -> None:
        self.top_k = top_k
        self.top_names = top_names
        self.route_calls = 0

    def route_result(self, query: str, context: Any = None) -> RoutingResult:  # noqa: ARG002
        self.route_calls += 1
        tools = [_scored(n) for n in self.top_names[: self.top_k]]
        return RoutingResult(
            tools=tools,
            top_k=self.top_k,
            confidence_top1=0.9,
            query=query,
        )

    def schemas(self, result: RoutingResult) -> list[dict[str, Any]]:
        out = []
        for s in result.tools:
            out.append(s.schema or _schema(s.name))
        return out


def _predictor(
    client: FakeDraftClient,
    *,
    top_names: list[str] | None = None,
    threshold: float = 0.75,
    n_tools: int = 46,
) -> ToolCallPredictor:
    names = top_names or ["search", "fetch_url", "list_objects"]
    return ToolCallPredictor(
        draft_client=client,
        registry=_registry(n_tools),
        semantic_router=FakeSemanticRouter(names),
        threshold=threshold,
        max_predictions=3,
    )


@pytest.fixture(autouse=True)
def _mcp_execute_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_MCP_EXECUTE", "0")
    monkeypatch.setenv("NSA_LLAMA_N_PROBS", "0")
    monkeypatch.setenv("NSA_LLAMA_N_PROBS_DEFAULT", "5")


@pytest.mark.asyncio
async def test_top_k_schemas_injected_not_full_registry() -> None:
    client = FakeDraftClient(
        content=json.dumps({"name": "search", "arguments": {"q": "x"}}),
        logprob=math.log(0.9),
    )
    top = ["search", "fetch_url", "list_objects"]
    pred = _predictor(client, top_names=top, n_tools=46)
    out = await pred.predict([{"role": "user", "content": "search docs"}])
    assert out and out[0].tool_name == "search"
    assert client.last_messages is not None
    blob = json.dumps(client.last_messages)
    for name in top:
        assert name in blob
    # Registry has tool_45 etc. — must NOT appear in draft prompt.
    assert "tool_45" not in blob
    assert "tool_40" not in blob
    assert client.last_messages[1]["content"].count('"name"') <= 6  # Top-K only


@pytest.mark.asyncio
async def test_parse_tool_tag_format() -> None:
    client = FakeDraftClient(content='<tool>search({"q": "arm"})</tool>', logprob=math.log(0.95))
    pred = _predictor(client)
    # Also unit-check parser directly.
    parsed = pred._parse_tool_call('<tool>search({"q": "arm"})</tool>')
    assert parsed is not None
    assert parsed.tool_name == "search"
    assert parsed.args == {"q": "arm"}
    out = await pred.predict([{"role": "user", "content": "find arm docs"}])
    assert len(out) == 1
    assert out[0].tool_name == "search"
    assert out[0].args["q"] == "arm"


@pytest.mark.asyncio
async def test_parse_json_array_tool_call() -> None:
    payload = [{"name": "echo", "arguments": {"text": "hello"}}]
    client = FakeDraftClient(content=json.dumps(payload), logprob=math.log(0.9))
    pred = _predictor(client)
    parsed = pred._parse_tool_call(json.dumps(payload))
    assert parsed is not None
    assert parsed.tool_name == "echo"
    assert parsed.args == {"text": "hello"}
    out = await pred.predict([{"role": "user", "content": "Use the echo tool to repeat the word hello."}])
    assert len(out) == 1
    assert out[0].tool_name == "echo"
    assert out[0].args["text"] == "hello"

    payload = {
        "tool_calls": [
            {
                "type": "function",
                "function": {
                    "name": "fetch_url",
                    "arguments": json.dumps({"url": "https://example.com"}),
                },
            }
        ]
    }
    client = FakeDraftClient(content=json.dumps(payload), logprob=math.log(0.92))
    pred = _predictor(client)
    parsed = pred._parse_tool_call(json.dumps(payload))
    assert parsed is not None
    assert parsed.tool_name == "fetch_url"
    assert parsed.args["url"] == "https://example.com"
    out = await pred.predict([{"role": "user", "content": "open example.com"}])
    assert out[0].tool_name == "fetch_url"


@pytest.mark.asyncio
async def test_parse_openai_message_tool_calls() -> None:
    client = FakeDraftClient(
        content="",
        tool_calls=[
            {
                "type": "function",
                "function": {"name": "list_objects", "arguments": '{"bucket":"b"}'},
            }
        ],
        logprob=math.log(0.9),
    )
    pred = _predictor(client)
    out = await pred.predict([{"role": "user", "content": "list bucket"}])
    assert out[0].tool_name == "list_objects"
    assert out[0].args["bucket"] == "b"


@pytest.mark.asyncio
async def test_confidence_threshold_filters() -> None:
    # Below threshold → []
    low = FakeDraftClient(
        content=json.dumps({"name": "search", "arguments": {"q": "x"}}),
        logprob=math.log(0.2),
    )
    pred_low = _predictor(low, threshold=0.75)
    assert await pred_low.predict([{"role": "user", "content": "q"}]) == []

    # Above threshold → kept
    high = FakeDraftClient(
        content=json.dumps({"name": "search", "arguments": {"q": "x"}}),
        logprob=math.log(0.9),
    )
    pred_high = _predictor(high, threshold=0.75)
    out = await pred_high.predict([{"role": "user", "content": "q"}])
    assert len(out) == 1
    assert out[0].confidence >= 0.75


@pytest.mark.asyncio
async def test_garbage_returns_empty_not_raise() -> None:
    client = FakeDraftClient(garbage=True, logprob=math.log(0.99))
    pred = _predictor(client)
    out = await pred.predict([{"role": "user", "content": "do something"}])
    assert out == []


@pytest.mark.asyncio
async def test_draft_exception_returns_empty() -> None:
    class BoomClient:
        async def generate_with_logits(self, *a: Any, **k: Any) -> dict[str, Any]:
            raise RuntimeError("llama down")

    pred = ToolCallPredictor(
        draft_client=BoomClient(),
        registry=_registry(3),
        semantic_router=FakeSemanticRouter(["search"]),
        threshold=0.5,
    )
    assert await pred.predict([{"role": "user", "content": "x"}]) == []


@pytest.mark.asyncio
async def test_latency_budget_2k_prompt_under_800ms() -> None:
    # Fake sleeps briefly; prompt ~2k tokens of filler still must finish <800ms.
    client = FakeDraftClient(
        content=json.dumps({"name": "search", "arguments": {"q": "ok"}}),
        logprob=math.log(0.9),
        sleep_s=0.05,
    )
    pred = _predictor(client)
    big = "word " * 2000  # ~2k-token-ish prompt body
    messages = [
        {"role": "user", "content": big},
        {"role": "assistant", "content": "ack"},
        {"role": "user", "content": "search now"},
    ]
    t0 = time.perf_counter()
    out = await pred.predict(messages)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert out and out[0].tool_name == "search"
    assert elapsed_ms < 800.0


@pytest.mark.asyncio
async def test_read_only_when_mcp_execute_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NSA_MCP_EXECUTE", "0")
    execute = MagicMock()
    client = FakeDraftClient(
        content=json.dumps({"name": "search", "arguments": {"q": "x"}}),
        logprob=math.log(0.9),
    )
    router = FakeSemanticRouter(["search"])
    router.execute = execute  # type: ignore[attr-defined]
    pred = ToolCallPredictor(
        draft_client=client,
        registry=_registry(5),
        semantic_router=router,
        threshold=0.5,
    )
    await pred.predict([{"role": "user", "content": "search"}])
    execute.assert_not_called()


def test_gateway_accepts_tool_predictor_field() -> None:
    from neuroswarm_arm.gateway import AgentGateway

    client = FakeDraftClient(content="{}", logprob=math.log(0.9))
    predictor = _predictor(client)
    gw = AgentGateway(
        registry=MagicMock(),
        semantic_router=MagicMock(),
        tool_router=MagicMock(),
        tool_predictor=predictor,
    )
    assert gw.tool_predictor is predictor
    assert gw.tool_router is not None
