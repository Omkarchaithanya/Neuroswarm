"""Tests for SpeculativeEngine (FakeCascade + FakePredictor + FakeExecutor)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from neuroswarm_arm.metrics.compat import MetricsStore
from neuroswarm_arm.runtime.dipa.speculative.engine import (
    SpeculativeEngine,
    empty_chat_response,
    generate_with_tool_speculation,
)
from neuroswarm_arm.runtime.dipa.speculative.executor import SpeculativeExecutor
from neuroswarm_arm.runtime.dipa.speculative.predictor import ToolPrediction
from neuroswarm_arm.runtime.dipa.speculative.tool_cache import ToolOutputCache
from neuroswarm_arm.schemas import ChatRequest, Message


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakePredictor:
    def __init__(
        self,
        preds: list[ToolPrediction] | None = None,
        *,
        delay_s: float = 0.0,
    ) -> None:
        self.preds = list(preds or [])
        self.delay_s = delay_s
        self.calls = 0

    async def predict(self, messages: list[dict]) -> list[ToolPrediction]:
        del messages
        self.calls += 1
        if self.delay_s > 0:
            await asyncio.sleep(self.delay_s)
        return list(self.preds)


class FakeCascade:
    """Async cascade stand-in. Emits optional tool_calls after ``delay_s``."""

    def __init__(
        self,
        *,
        delay_s: float = 0.05,
        tool_name: str | None = None,
        tool_args: dict[str, Any] | None = None,
        content: str = "cascade-ok",
        normal_execute: Any | None = None,
    ) -> None:
        self.delay_s = delay_s
        self.tool_name = tool_name
        self.tool_args = dict(tool_args or {})
        self.content = content
        self.normal_execute = normal_execute
        self.calls = 0
        self.normal_path_calls = 0

    async def generate(self, request: ChatRequest) -> Any:
        del request
        self.calls += 1
        await asyncio.sleep(self.delay_s)
        tool_calls: list[dict[str, object]] = []
        if self.tool_name:
            tool_calls.append(
                {
                    "type": "function",
                    "function": {
                        "name": self.tool_name,
                        "arguments": self.tool_args,
                    },
                }
            )
        return empty_chat_response(
            content=self.content,
            tool_calls=tool_calls or None,
        )


class FakeMCPManager:
    def __init__(self, *, result: Any = None, delay_s: float = 0.0) -> None:
        self.result = result if result is not None else {"ok": True, "result": "mcp"}
        self.delay_s = delay_s
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.cancelled = False

    async def execute(self, tool_name: str, args: dict[str, Any], **kwargs: Any) -> Any:
        del kwargs
        self.calls.append((tool_name, dict(args)))
        try:
            await asyncio.sleep(self.delay_s)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self.result


def _req(text: str = "search docs") -> ChatRequest:
    return ChatRequest(messages=[Message(role="user", content=text)])


def _pred(
    name: str = "search",
    args: dict[str, Any] | None = None,
    conf: float = 0.95,
) -> ToolPrediction:
    return ToolPrediction(tool_name=name, args=args or {"q": "arm"}, confidence=conf)


@pytest.fixture
def cache() -> ToolOutputCache:
    return ToolOutputCache(max_size=64, ttl_seconds=300)


@pytest.fixture
def metrics() -> MetricsStore:
    return MetricsStore()


def _engine(
    *,
    predictor: FakePredictor,
    cascade: FakeCascade,
    cache: ToolOutputCache,
    metrics: MetricsStore,
    mcp: FakeMCPManager | None = None,
    tool_timeout_s: float = 5.0,
    threshold: float = 0.75,
) -> tuple[SpeculativeEngine, FakeMCPManager, SpeculativeExecutor]:
    mcp = mcp or FakeMCPManager()
    executor = SpeculativeExecutor(
        mcp, cache, asyncio.Semaphore(4), tool_timeout_s=tool_timeout_s
    )
    eng = SpeculativeEngine(
        predictor,
        executor,
        cascade,
        cache,
        metrics,
        tool_timeout_s=tool_timeout_s,
        threshold=threshold,
    )
    return eng, mcp, executor


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hit_returns_immediately_no_extra_mcp(
    cache: ToolOutputCache, metrics: MetricsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NSA_TOOL_SPEC_THRESHOLD", "0.75")
    key = cache.make_key("search", {"q": "arm"})
    await cache.set(key, '{"ok":true,"result":"cached"}')

    mcp = FakeMCPManager(delay_s=10.0)  # would hang if called
    pred = FakePredictor([_pred()], delay_s=0.0)
    cascade = FakeCascade(delay_s=0.08, tool_name="search", tool_args={"q": "arm"})
    eng, mcp, _ex = _engine(
        predictor=pred, cascade=cascade, cache=cache, metrics=metrics, mcp=mcp
    )

    resp = await eng.generate(_req())

    assert resp.speculative_hit is True
    assert "cached" in resp.content
    assert mcp.calls == []  # cache hit on dispatch — no MCP
    assert metrics.counters.get("neuroswarm_tool_spec_hit_total", 0) >= 1


@pytest.mark.asyncio
async def test_miss_no_tool_call_cancels_speculative(
    cache: ToolOutputCache, metrics: MetricsStore
) -> None:
    mcp = FakeMCPManager(delay_s=5.0)
    pred = FakePredictor([_pred()], delay_s=0.0)
    # Cascade finishes WITHOUT a tool call.
    cascade = FakeCascade(delay_s=0.05, tool_name=None, content="plain text")
    eng, mcp, ex = _engine(
        predictor=pred,
        cascade=cascade,
        cache=cache,
        metrics=metrics,
        mcp=mcp,
        tool_timeout_s=30.0,
    )

    # Give predict+speculate a head start before awaiting generate.
    resp = await generate_with_tool_speculation(eng, _req())

    assert resp.speculative_hit is False
    assert resp.content == "plain text"
    assert metrics.counters.get("neuroswarm_tool_spec_miss_total", 0) >= 1
    await asyncio.sleep(0.05)
    # Speculative MCP started then cancelled (wrong — cascade had no tool_call).
    assert mcp.cancelled is True


@pytest.mark.asyncio
async def test_race_await_in_flight_speculative(
    cache: ToolOutputCache, metrics: MetricsStore
) -> None:
    """Predictor correct; cascade emits tool_call before MCP finishes → await + use."""
    mcp = FakeMCPManager(delay_s=0.15, result={"ok": True, "result": "spec-ok"})
    pred = FakePredictor([_pred()], delay_s=0.0)
    # Cascade finishes tool_call emission quickly; MCP still running.
    cascade = FakeCascade(delay_s=0.03, tool_name="search", tool_args={"q": "arm"})
    eng, mcp, _ex = _engine(
        predictor=pred,
        cascade=cascade,
        cache=cache,
        metrics=metrics,
        mcp=mcp,
        tool_timeout_s=2.0,
    )

    resp = await eng.generate(_req())

    assert resp.speculative_hit is True
    assert "spec-ok" in resp.content
    assert len(mcp.calls) == 1  # only the speculative call — no fallthrough extra
    assert metrics.counters.get("neuroswarm_tool_spec_hit_total", 0) >= 1
    assert metrics.counters.get("neuroswarm_tool_spec_time_saved_ms_total", 0) >= 0


@pytest.mark.asyncio
async def test_race_wrong_tool_cancelled_normal_path(
    cache: ToolOutputCache, metrics: MetricsStore
) -> None:
    """Predictor wrong tool → cancel speculative; normal path runs correct tool."""
    mcp = FakeMCPManager(delay_s=0.2, result={"ok": True, "result": "sync-ok"})
    pred = FakePredictor([_pred("wrong_tool", {"x": 1})], delay_s=0.0)
    cascade = FakeCascade(
        delay_s=0.05, tool_name="search", tool_args={"q": "arm"}
    )
    eng, mcp, _ex = _engine(
        predictor=pred,
        cascade=cascade,
        cache=cache,
        metrics=metrics,
        mcp=mcp,
        tool_timeout_s=2.0,
    )

    resp = await eng.generate(_req())

    assert resp.speculative_hit is False
    assert metrics.counters.get("neuroswarm_tool_spec_miss_total", 0) >= 1
    # Wrong-tool speculative cancelled; correct tool executed on fallthrough.
    names = [c[0] for c in mcp.calls]
    assert "search" in names
    assert mcp.cancelled is True or "wrong_tool" in names
    assert "sync-ok" in resp.content or resp.content == "cascade-ok"


@pytest.mark.asyncio
async def test_cancellation_cleans_up_tasks(
    cache: ToolOutputCache, metrics: MetricsStore
) -> None:
    mcp = FakeMCPManager(delay_s=10.0)
    pred = FakePredictor(
        [_pred("a", {"i": 1}), _pred("b", {"i": 2})],
        delay_s=0.0,
    )
    cascade = FakeCascade(delay_s=0.04, tool_name=None, content="done")
    eng, mcp, ex = _engine(
        predictor=pred,
        cascade=cascade,
        cache=cache,
        metrics=metrics,
        mcp=mcp,
        tool_timeout_s=30.0,
        threshold=0.5,
    )

    resp = await eng.generate(_req())
    await asyncio.sleep(0.05)

    assert resp.speculative_hit is False
    assert mcp.cancelled is True
    assert metrics.counters.get("neuroswarm_tool_spec_miss_total", 0) >= 1


@pytest.mark.asyncio
async def test_metrics_three_counters_wired(
    cache: ToolOutputCache, metrics: MetricsStore
) -> None:
    key = cache.make_key("search", {"q": "arm"})
    await cache.set(key, '{"ok":true,"result":"hit"}')
    pred = FakePredictor([_pred()], delay_s=0.0)
    cascade = FakeCascade(delay_s=0.05, tool_name="search", tool_args={"q": "arm"})
    eng, _mcp, _ex = _engine(
        predictor=pred, cascade=cascade, cache=cache, metrics=metrics
    )

    await eng.generate(_req())

    assert "neuroswarm_tool_spec_hit_total" in metrics.counters
    assert "neuroswarm_tool_spec_miss_total" in metrics.counters
    assert "neuroswarm_tool_spec_time_saved_ms_total" in metrics.counters
    assert metrics.counters["neuroswarm_tool_spec_hit_total"] >= 1
    assert metrics.counters["neuroswarm_tool_spec_time_saved_ms_total"] >= 0


@pytest.mark.asyncio
async def test_below_threshold_skips_speculate(
    cache: ToolOutputCache, metrics: MetricsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NSA_TOOL_SPEC_THRESHOLD", "0.90")
    mcp = FakeMCPManager(delay_s=0.0, result={"ok": True, "result": "sync"})
    pred = FakePredictor([_pred(conf=0.5)], delay_s=0.0)
    cascade = FakeCascade(delay_s=0.03, tool_name="search", tool_args={"q": "arm"})
    eng, mcp, _ex = _engine(
        predictor=pred,
        cascade=cascade,
        cache=cache,
        metrics=metrics,
        mcp=mcp,
        threshold=0.90,
    )

    resp = await eng.generate(_req())
    assert resp.speculative_hit is False
    # Fallthrough sync execute only (no speculative dispatch for low conf).
    assert all(c[0] == "search" for c in mcp.calls)
