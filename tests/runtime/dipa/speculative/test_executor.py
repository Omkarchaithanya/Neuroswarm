"""Tests for SpeculativeExecutor (fake MCP manager — no real MCP)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from neuroswarm_arm.runtime.dipa.speculative.executor import SpeculativeExecutor
from neuroswarm_arm.runtime.dipa.speculative.predictor import ToolPrediction
from neuroswarm_arm.runtime.dipa.speculative.tool_cache import ToolOutputCache


class FakeMCPManager:
    """Stand-in for mcp_executor execute path."""

    def __init__(
        self,
        *,
        result: Any = None,
        delay_s: float = 0.0,
        error: Exception | None = None,
        disabled: bool = False,
    ) -> None:
        self.result = result if result is not None else {"ok": True, "result": "pong"}
        self.delay_s = delay_s
        self.error = error
        self.disabled = disabled
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.cancelled = False
        self._active = 0
        self.max_active = 0
        self._lock = asyncio.Lock()

    async def execute(self, tool_name: str, args: dict[str, Any], **kwargs: Any) -> Any:
        del kwargs
        self.calls.append((tool_name, dict(args)))
        async with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        try:
            if self.disabled:
                return {
                    "ok": False,
                    "error": (
                        "MCP execute disabled. Set NSA_MCP_EXECUTE=1 "
                        "to enable template server calls."
                    ),
                    "tool_id": tool_name,
                    "status": 503,
                }
            if self.error is not None:
                raise self.error
            try:
                await asyncio.sleep(self.delay_s)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            return self.result
        finally:
            async with self._lock:
                self._active -= 1


@pytest.fixture
def cache() -> ToolOutputCache:
    return ToolOutputCache(max_size=64, ttl_seconds=300)


def _pred(name: str = "echo", args: dict[str, Any] | None = None) -> ToolPrediction:
    return ToolPrediction(tool_name=name, args=args or {"q": "hi"}, confidence=0.95)


@pytest.mark.asyncio
async def test_cache_hit_short_circuits_no_mcp(cache: ToolOutputCache) -> None:
    mcp = FakeMCPManager()
    key = cache.make_key("echo", {"q": "hi"})
    await cache.set(key, '{"ok":true,"result":"cached"}')

    ex = SpeculativeExecutor(mcp, cache, asyncio.Semaphore(2), tool_timeout_s=5.0)
    task = await ex.speculate(_pred())
    assert task.cache_hit_on_dispatch is True
    out = await ex.await_result(task, key)
    assert out == '{"ok":true,"result":"cached"}'
    assert mcp.calls == []


@pytest.mark.asyncio
async def test_cache_miss_fires_mcp_and_writes_cache(cache: ToolOutputCache) -> None:
    mcp = FakeMCPManager(result={"ok": True, "result": "fresh"})
    ex = SpeculativeExecutor(mcp, cache, asyncio.Semaphore(2))
    pred = _pred("search", {"q": "arm"})
    key = cache.make_key(pred.tool_name, pred.args)

    task = await ex.speculate(pred)
    assert task.cache_hit_on_dispatch is False
    out = await ex.await_result(task, key)

    assert len(mcp.calls) == 1
    assert mcp.calls[0] == ("search", {"q": "arm"})
    assert out is not None
    assert "fresh" in out
    assert await cache.get(key) == out


@pytest.mark.asyncio
async def test_timeout_cancels_underlying_task(cache: ToolOutputCache) -> None:
    mcp = FakeMCPManager(delay_s=10.0)
    ex = SpeculativeExecutor(mcp, cache, asyncio.Semaphore(2), tool_timeout_s=0.05)
    pred = _pred("slow", {"n": 1})
    task = await ex.speculate(pred)
    out = await ex.await_result(task, task.key)

    assert out is None
    assert mcp.cancelled is True
    assert task.future.done()
    assert not task.future.cancelled()  # completed with None after wait_for


@pytest.mark.asyncio
async def test_cancel_propagates_to_speculative_task(cache: ToolOutputCache) -> None:
    mcp = FakeMCPManager(delay_s=10.0)
    ex = SpeculativeExecutor(mcp, cache, asyncio.Semaphore(2), tool_timeout_s=30.0)
    task = await ex.speculate(_pred("long", {"n": 2}))
    # Let the MCP call enter sleep
    await asyncio.sleep(0.02)
    ex.cancel(task)
    out = await ex.await_result(task, task.key)

    assert out is None
    assert task.future.cancelled() or mcp.cancelled
    assert mcp.cancelled is True


@pytest.mark.asyncio
async def test_concurrent_speculates_honor_semaphore(cache: ToolOutputCache) -> None:
    mcp = FakeMCPManager(delay_s=0.08, result={"ok": True, "result": "ok"})
    sem = asyncio.Semaphore(2)
    ex = SpeculativeExecutor(mcp, cache, sem, tool_timeout_s=5.0)

    preds = [_pred(f"t{i}", {"i": i}) for i in range(6)]
    tasks = await asyncio.gather(*(ex.speculate(p) for p in preds))
    outs = await asyncio.gather(*(ex.await_result(t, t.key) for t in tasks))

    assert all(o is not None for o in outs)
    assert mcp.max_active <= 2
    assert len(mcp.calls) == 6


@pytest.mark.asyncio
async def test_disabled_mcp_no_local_gate_passthrough(cache: ToolOutputCache) -> None:
    """NSA_MCP_EXECUTE=0 → manager returns 503-style payload; we do not gate."""
    mcp = FakeMCPManager(disabled=True)
    ex = SpeculativeExecutor(mcp, cache, asyncio.Semaphore(2))
    pred = _pred("github.list_issues", {"repo": "a/b"})
    task = await ex.speculate(pred)
    out = await ex.await_result(task, task.key)

    assert len(mcp.calls) == 1
    assert out is not None
    assert "NSA_MCP_EXECUTE" in out
    assert "503" in out or '"ok":false' in out.replace(" ", "")
    # Failed execute must not poison cache
    assert await cache.get(task.key) is None
