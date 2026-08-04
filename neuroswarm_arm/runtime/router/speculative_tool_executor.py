"""Speculative tool execution — run predicted calls in parallel, cache results.

Layer sits between predictor + mcp_executor; gateway calls confirm() after
main model emits tool_call. Optional: disable via NSA_SPEC_TOOL_ENABLED=0.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

from .mcp_executor import call_tool
from .tool_call_predictor import DraftCall, ToolCallPredictor
from .tool_output_cache import ToolOutputCache


def _env_bool(name: str, default: bool = True) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


_SPEC_ENABLED = _env_bool("NSA_SPEC_TOOL_ENABLED", True)
_SPEC_INFLIGHT = _env_int("NSA_SPEC_TOOL_INFLIGHT", 4)
_SPEC_TIMEOUT_MS = _env_int("NSA_SPEC_TOOL_TIMEOUT_MS", 5000)


@dataclass(slots=True)
class SpeculativeResult:
    speculative_id: str        # uuid4 hex[:12]
    tool_id: str
    arguments: dict[str, Any]
    score: float
    backend: str               # "cache" | "embedding" | "tier1_llm"
    result: dict[str, Any] | None
    error: str | None
    latency_ms: float
    is_cache_hit: bool


class SpeculativeToolExecutor:
    """Run predicted tool calls speculatively; cache results for instant confirm."""

    def __init__(
        self,
        *,
        cache: ToolOutputCache | None,
        predictor: ToolCallPredictor | None,
        max_inflight: int = _SPEC_INFLIGHT,
    ) -> None:
        self._cache = cache
        self._predictor = predictor
        self._max_inflight = max(1, max_inflight)
        self._enabled = _SPEC_ENABLED and cache is not None and predictor is not None
        self._spec_total = 0
        self._cache_hits = 0
        self._confirmed_hits = 0
        self._prediction_latencies: list[float] = []
        self._pending: dict[str, SpeculativeResult] = {}
        self._lock = asyncio.Lock()

    async def speculate(
        self,
        query: str,
        *,
        context: dict[str, Any] | None = None,
        session_id: str,
    ) -> list[SpeculativeResult]:
        if not self._enabled:
            return []

        t_start = time.perf_counter()
        drafts = self._predictor.predict(query, context=context)
        pred_latency = (time.perf_counter() - t_start) * 1000.0
        self._prediction_latencies.append(pred_latency)
        if len(self._prediction_latencies) > 1000:
            self._prediction_latencies = self._prediction_latencies[-1000:]

        results: list[SpeculativeResult] = []
        to_execute: list[tuple[DraftCall, str]] = []  # (draft, speculative_id)

        for draft in drafts:
            spec_id = uuid.uuid4().hex[:12]
            self._spec_total += 1

            cached = self._cache.get(draft.tool_id, draft.arguments)
            if cached is not None:
                self._cache_hits += 1
                results.append(
                    SpeculativeResult(
                        speculative_id=spec_id,
                        tool_id=draft.tool_id,
                        arguments=draft.arguments,
                        score=draft.score,
                        backend=draft.backend,
                        result=cached,
                        error=None,
                        latency_ms=0.0,
                        is_cache_hit=True,
                    )
                )
                async with self._lock:
                    self._pending[spec_id] = results[-1]
                continue

            to_execute.append((draft, spec_id))

        if to_execute:
            sem = asyncio.Semaphore(self._max_inflight)

            async def run_one(draft: DraftCall, spec_id: str) -> SpeculativeResult:
                async with sem:
                    t0 = time.perf_counter()
                    try:
                        result = await asyncio.wait_for(
                            call_tool(draft.tool_id, draft.arguments),
                            timeout=_SPEC_TIMEOUT_MS / 1000.0,
                        )
                        latency = (time.perf_counter() - t0) * 1000.0
                        err = None
                        if not result.get("ok"):
                            err = result.get("error") or "tool_error"
                    except asyncio.TimeoutError:
                        latency = (time.perf_counter() - t0) * 1000.0
                        result = {"ok": False, "error": "speculative_timeout"}
                        err = "timeout"
                    except Exception as exc:
                        latency = (time.perf_counter() - t0) * 1000.0
                        result = {"ok": False, "error": str(exc)}
                        err = str(exc)

                    self._cache.put(draft.tool_id, draft.arguments, result)

                    spec_res = SpeculativeResult(
                        speculative_id=spec_id,
                        tool_id=draft.tool_id,
                        arguments=draft.arguments,
                        score=draft.score,
                        backend=draft.backend,
                        result=result,
                        error=err,
                        latency_ms=latency,
                        is_cache_hit=False,
                    )
                    async with self._lock:
                        self._pending[spec_id] = spec_res
                    return spec_res

            executed = await asyncio.gather(
                *[run_one(d, sid) for d, sid in to_execute], return_exceptions=True
            )
            for r in executed:
                if isinstance(r, SpeculativeResult):
                    results.append(r)
                elif isinstance(r, Exception):
                    pass

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def confirm(
        self, speculative_id: str, *, tool_id: str, arguments: dict[str, Any]
    ) -> dict[str, Any] | None:
        if not self._enabled:
            return None

        spec = self._pending.pop(speculative_id, None)
        if spec is None:
            return None
        if spec.tool_id != tool_id or spec.arguments != arguments:
            return None

        self._confirmed_hits += 1
        return spec.result

    def stats(self) -> dict[str, Any]:
        lat = sorted(self._prediction_latencies)
        def pct(p: float) -> float:
            if not lat:
                return 0.0
            idx = int(len(lat) * p)
            return lat[min(idx, len(lat) - 1)]

        return {
            "speculative_total": self._spec_total,
            "cache_hits": self._cache_hits,
            "confirmed_hits": self._confirmed_hits,
            "prediction_latency_ms_p50": pct(0.50),
            "prediction_latency_ms_p95": pct(0.95),
            "enabled": self._enabled,
        }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    import asyncio
    from unittest.mock import AsyncMock, patch

    from neuroswarm_arm.runtime.router.tool_call_predictor import (
        ToolCallPredictor,
        DraftCall,
        _FakeEmbedder,
        _build_demo_registry,
    )

    registry = _build_demo_registry()
    embedder = _FakeEmbedder()

    cache = ToolOutputCache(max_entries=100, ttl_s=60, neg_ttl_s=10)

    class _MockPredictor:
        def __init__(self):
            self.drafts = [
                DraftCall(
                    tool_id="foo.search",
                    arguments={"query": "test"},
                    score=0.9,
                    backend="embedding",
                    latency_ms=1.0,
                ),
                DraftCall(
                    tool_id="foo.write",
                    arguments={"text": "hello"},
                    score=0.8,
                    backend="embedding",
                    latency_ms=1.0,
                ),
            ]

        def predict(self, query: str, *, context: dict | None = None) -> list[DraftCall]:
            return self.drafts

    predictor = _MockPredictor()

    mock_call_tool = AsyncMock(return_value={"ok": True, "result": {"data": "ok"}})

    async def run_test():
        with patch("neuroswarm_arm.runtime.router.speculative_tool_executor.call_tool", mock_call_tool):
            exec_ = SpeculativeToolExecutor(cache=cache, predictor=predictor, max_inflight=4)

            # First call — no cache
            r1 = await exec_.speculate("test query", session_id="s1")
            print(f"First call: {len(r1)} results, cache_hits={sum(1 for r in r1 if r.is_cache_hit)}")
            print(f"mock_call_tool.call_count after first: {mock_call_tool.call_count}")
            assert len(r1) == 2
            assert sum(1 for r in r1 if r.is_cache_hit) == 0
            assert mock_call_tool.call_count == 2

            # Second call — all cache hits
            r2 = await exec_.speculate("test query", session_id="s1")
            print(f"Second call: {len(r2)} results, cache_hits={sum(1 for r in r2 if r.is_cache_hit)}")
            print(f"mock_call_tool.call_count after second: {mock_call_tool.call_count}")
            assert len(r2) == 2
            assert sum(1 for r in r2 if r.is_cache_hit) == 2
            assert mock_call_tool.call_count == 2  # no new calls

            # Test confirm
            spec_id = r2[0].speculative_id
            tool_id = r2[0].tool_id
            args = r2[0].arguments
            confirmed = exec_.confirm(spec_id, tool_id=tool_id, arguments=args)
            assert confirmed is not None
            assert confirmed.get("ok") is True

            # Wrong args -> None
            assert exec_.confirm(spec_id, tool_id=tool_id, arguments={"query": "diff"}) is None

            stats = exec_.stats()
            print(f"Stats: {stats}")
            assert stats["speculative_total"] == 4  # 2 + 2
            assert stats["cache_hits"] == 2
            assert stats["confirmed_hits"] == 1

            print("All self-tests passed!")

    asyncio.run(run_test())