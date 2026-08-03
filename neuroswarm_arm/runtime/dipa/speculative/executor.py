"""Speculative MCP executor — fire tool calls ahead of the Actor.

When the draft Speculator emits a high-confidence ``ToolPrediction``, this
wrapper starts the real MCP call **asynchronously** while Tier 2/3 still
generates. Results land in ``ToolOutputCache`` for later reuse.

Reuses the injected MCP manager execute path as-is (no local
``NSA_MCP_EXECUTE`` gate). Safe alongside ``mcp_executor.McpServerManager``
via a shared ``asyncio.Semaphore`` for speculative inflight caps.

References:
  - arXiv:2512.15834 (Nichols et al., Speculative Tool Calling)
  - arXiv:2510.04371 (Ye et al., Speculative Actions)
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

from .predictor import ToolPrediction
from .tool_cache import ToolOutputCache


class SupportsMcpExecute(Protocol):
    """Duck-type for ``MCPManager.execute`` / test fakes."""

    async def execute(
        self, tool_name: str, args: dict[str, Any], **kwargs: Any
    ) -> Any: ...


@dataclass(slots=True)
class SpeculativeTask:
    """In-flight (or cache-hit) speculative tool invocation."""

    tool_name: str
    args: dict[str, Any]
    key: str
    future: asyncio.Task[str | None]
    started_at: float
    finished_at: float | None = None
    cache_hit_on_dispatch: bool = False


class SpeculativeExecutor:
    """Thin async wrapper: cache short-circuit + bounded speculative MCP fire."""

    def __init__(
        self,
        mcp_manager: SupportsMcpExecute,
        cache: ToolOutputCache,
        inflight_sem: asyncio.Semaphore,
        tool_timeout_s: float = 5.0,
    ) -> None:
        self._mcp_manager = mcp_manager
        self._cache = cache
        self._inflight_sem = inflight_sem
        self._tool_timeout_s = float(tool_timeout_s)

    async def speculate(self, pred: ToolPrediction) -> SpeculativeTask:
        """Dispatch speculative call (or cache hit). Returns immediately."""
        started = time.perf_counter()
        key = self._cache.make_key(pred.tool_name, pred.args)
        cached = await self._cache.get(key)
        if cached is not None:
            fut = asyncio.create_task(self._immediate(cached))
            return SpeculativeTask(
                tool_name=pred.tool_name,
                args=dict(pred.args),
                key=key,
                future=fut,
                started_at=started,
                finished_at=time.perf_counter(),
                cache_hit_on_dispatch=True,
            )

        fut = asyncio.create_task(
            self._run_mcp(pred.tool_name, dict(pred.args), key)
        )
        return SpeculativeTask(
            tool_name=pred.tool_name,
            args=dict(pred.args),
            key=key,
            future=fut,
            started_at=started,
            cache_hit_on_dispatch=False,
        )

    async def await_result(self, task: SpeculativeTask, key: str) -> str | None:
        """Wait for speculative result; ``None`` on cancel/timeout/failure."""
        try:
            out = await task.future
        except asyncio.CancelledError:
            task.finished_at = time.perf_counter()
            return None
        except Exception:  # noqa: BLE001 — speculative path never raises
            task.finished_at = time.perf_counter()
            return None
        task.finished_at = time.perf_counter()
        # Caller key may differ from dispatch key; mirror successful payload.
        if out is not None and key != task.key and not task.cache_hit_on_dispatch:
            await self._cache.set(key, out)
        return out

    def cancel(self, task: SpeculativeTask) -> None:
        """Cancel underlying asyncio task (propagates to MCP await)."""
        if not task.future.done():
            task.future.cancel()

    @staticmethod
    async def _immediate(value: str) -> str:
        return value

    async def _run_mcp(
        self, tool_name: str, args: dict[str, Any], key: str
    ) -> str | None:
        async def _body() -> str | None:
            async with self._inflight_sem:
                try:
                    raw = await asyncio.wait_for(
                        self._mcp_manager.execute(tool_name, args),
                        timeout=self._tool_timeout_s,
                    )
                except asyncio.TimeoutError:
                    return None
                except Exception:  # noqa: BLE001
                    return None
            value = _serialize(raw)
            if _is_success(raw):
                # Persist even if the SpeculativeTask is cancelled (Actor miss).
                await self._cache.set(key, value)
            return value

        task = asyncio.create_task(_body())
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Py3.11+ sticky cancel would abort a bare `await task`.
            current = asyncio.current_task()
            if current is not None and hasattr(current, "uncancel"):
                current.uncancel()
            try:
                return await asyncio.shield(task)
            except Exception:  # noqa: BLE001
                return None


def _serialize(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    return json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _is_success(raw: Any) -> bool:
    if isinstance(raw, dict) and "ok" in raw:
        return bool(raw["ok"])
    return raw is not None
