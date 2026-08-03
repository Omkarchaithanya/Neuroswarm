"""Speculative tool-call engine — arXiv 2512.15834 Section 4 algorithm.

Combine draft predictor (B2) + speculative executor (B3) into one async path
the gateway calls instead of going straight to the cascade:

1. Kick off ``predictor.predict(messages)`` AND ``cascade.generate(...)`` in
   parallel as two ``asyncio.Task``s.
2. While the cascade is running, for each high-confidence prediction
   (``confidence >= NSA_TOOL_SPEC_THRESHOLD``, default 0.75):
   a. If cache hit → mark ``cache_hit=True`` and capture value (via executor).
   b. Else → ``executor.speculate(pred)`` (returns a ``SpeculativeTask``).
3. When the cascade emits a tool_call:
   a. Compute its canonical key.
   b. If a ``SpeculativeTask`` with that key exists AND finished → return its
      output immediately, tag ``speculative_hit=true``, log
      ``neuroswarm_tool_spec_hit_total``.
   c. If a ``SpeculativeTask`` exists but not finished → await it (bounded by
      ``tool_timeout_s``), then return.
   d. Else → fall through to normal synchronous execution.
4. If the cascade finishes WITHOUT a tool call, cancel all in-flight
   speculative tasks (they were wrong) and return the cascade result.

References:
  - arXiv:2512.15834 (Nichols et al., Speculative Tool Calls)
  - arXiv:2510.04371 (Ye et al., Speculative Actions)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import deque
from typing import Any, Protocol

from neuroswarm_arm.schemas import ChatChoice, ChatRequest, ChatResponse, ChatUsage, Message

from .executor import SpeculativeExecutor, SpeculativeTask
from .predictor import ToolPrediction
from .tool_cache import ToolOutputCache

_METRIC_HIT = "neuroswarm_tool_spec_hit_total"
_METRIC_MISS = "neuroswarm_tool_spec_miss_total"
_METRIC_SAVED = "neuroswarm_tool_spec_time_saved_ms_total"
_METRIC_INFLIGHT = "neuroswarm_tool_spec_inflight"

_DEFAULT_THRESHOLD = 0.75
_DEBUG_MAX = 200


class SupportsPredict(Protocol):
    async def predict(self, messages: list[dict]) -> list[ToolPrediction]: ...


class SupportsCascadeGenerate(Protocol):
    async def generate(self, request: ChatRequest) -> ChatResponse: ...


class SupportsMetrics(Protocol):
    def inc(self, name: str, value: float = 1.0) -> None: ...

    def describe(self, name: str, metric_type: str, help_text: str) -> None: ...

    def set(self, name: str, value: float) -> None: ...


class SpeculativeEngine:
    """Parallel predict + cascade generate with speculative MCP overlap."""

    def __init__(
        self,
        predictor: SupportsPredict,
        executor: SpeculativeExecutor,
        cascade: SupportsCascadeGenerate,
        cache: ToolOutputCache,
        metrics: SupportsMetrics,
        *,
        tool_timeout_s: float | None = None,
        threshold: float | None = None,
    ) -> None:
        self._predictor = predictor
        self._executor = executor
        self._cascade = cascade
        self._cache = cache
        self._metrics = metrics
        self._tool_timeout_s = float(
            tool_timeout_s
            if tool_timeout_s is not None
            else getattr(executor, "_tool_timeout_s", 5.0)
        )
        self._threshold = float(
            threshold if threshold is not None else _threshold_from_env()
        )
        self.debug_events: deque[dict[str, Any]] = deque(maxlen=_DEBUG_MAX)
        self._register_metrics()

    def _register_metrics(self) -> None:
        self._metrics.describe(
            _METRIC_HIT, "counter", "Speculative tool-call cache/spec hits."
        )
        self._metrics.describe(
            _METRIC_MISS, "counter", "Speculative tool-call misses (fallthrough/cancel)."
        )
        self._metrics.describe(
            _METRIC_SAVED,
            "counter",
            "Milliseconds saved by speculative tool-call overlap.",
        )
        self._metrics.describe(
            _METRIC_INFLIGHT, "gauge", "In-flight speculative tool executions."
        )
        self._metrics.inc(_METRIC_HIT, 0.0)
        self._metrics.inc(_METRIC_MISS, 0.0)
        self._metrics.inc(_METRIC_SAVED, 0.0)
        self._metrics.set(_METRIC_INFLIGHT, 0.0)

    def record_debug(self, event: dict[str, Any]) -> None:
        payload = dict(event)
        payload.setdefault("ts", time.time())
        self.debug_events.append(payload)

    def debug_snapshot(self, *, reset: bool = False) -> list[dict[str, Any]]:
        snap = list(self.debug_events)
        if reset:
            self.debug_events.clear()
        return snap

    async def generate(self, request: ChatRequest) -> ChatResponse:
        """Run Section 4 algorithm; return ChatResponse (possibly speculative_hit)."""
        return await generate_with_tool_speculation(self, request)


async def generate_with_tool_speculation(
    engine: SpeculativeEngine,
    request: ChatRequest,
) -> ChatResponse:
    """Gateway entry: predictor ∥ cascade, then match speculative MCP results."""
    messages = _messages_as_dicts(request)

    pred_task: asyncio.Task[list[ToolPrediction]] = asyncio.create_task(
        engine._predictor.predict(messages)
    )
    cascade_task: asyncio.Task[ChatResponse] = asyncio.create_task(
        engine._cascade.generate(request)
    )

    spec_by_key: dict[str, SpeculativeTask] = {}

    async def _dispatch_predictions() -> None:
        try:
            preds = await pred_task
        except Exception:  # noqa: BLE001 — never block Actor path
            return
        # Always fire high-conf specs for cache warming — even if Actor already done.
        for pred in preds or []:
            if float(getattr(pred, "confidence", 0.0) or 0.0) < engine._threshold:
                continue
            try:
                task = await engine._executor.speculate(pred)
            except Exception:  # noqa: BLE001
                continue
            spec_by_key[task.key] = task

    dispatch_task = asyncio.create_task(_dispatch_predictions())

    try:
        cascade_resp = await cascade_task
    except Exception:
        await _cancel_task(dispatch_task)
        await _cancel_task(pred_task)
        _cancel_all(engine, spec_by_key)
        raise

    # Let in-flight dispatch finish (or exit early once cascade done).
    await _await_quiet(dispatch_task)
    if not pred_task.done():
        await _cancel_task(pred_task)

    emit_at = time.perf_counter()
    tool_call = _extract_tool_call(cascade_resp)

    engine._metrics.set(_METRIC_INFLIGHT, float(len(spec_by_key)))

    if tool_call is None:
        # Let MCP+cache land before cancelling leftovers (Actor had no tool_call).
        await _drain_specs(spec_by_key, timeout_s=min(2.0, engine._tool_timeout_s))
        _cancel_all(engine, spec_by_key)
        engine._metrics.inc(_METRIC_MISS)
        engine._metrics.set(_METRIC_INFLIGHT, 0.0)
        engine.record_debug({"event": "miss", "reason": "no_tool_call"})
        return _with_spec_flags(cascade_resp, hit=False, saved_ms=0.0)

    key = engine._cache.make_key(tool_call.tool_name, tool_call.args)
    matched = spec_by_key.pop(key, None)
    # Wrong-key specs are wrong — cancel immediately.
    _cancel_all(engine, spec_by_key)
    engine._metrics.set(_METRIC_INFLIGHT, 1.0 if matched is not None else 0.0)

    if matched is not None:
        if matched.future.done() and not matched.future.cancelled():
            out = _task_result(matched)
            if out is not None:
                saved = _latency_saved_ms(matched, emit_at)
                engine._metrics.set(_METRIC_INFLIGHT, 0.0)
                return _hit(engine, cascade_resp, out, saved, tool_call=tool_call)

        # In-flight: await within timeout (race: cascade emitted before MCP done).
        try:
            out = await asyncio.wait_for(
                engine._executor.await_result(matched, key),
                timeout=engine._tool_timeout_s,
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            engine._executor.cancel(matched)
            out = None
        if out is not None:
            saved = _latency_saved_ms(matched, time.perf_counter())
            engine._metrics.set(_METRIC_INFLIGHT, 0.0)
            return _hit(engine, cascade_resp, out, saved, tool_call=tool_call)

    # Miss / fallthrough → normal synchronous execution via public executor path.
    engine._metrics.inc(_METRIC_MISS)
    engine._metrics.set(_METRIC_INFLIGHT, 0.0)
    engine.record_debug(
        {
            "event": "miss",
            "tool": tool_call.tool_name,
            "args": dict(tool_call.args),
            "key": key,
        }
    )
    sync_out = await _sync_execute(engine, tool_call)
    if sync_out is not None:
        return _with_spec_flags(
            cascade_resp.model_copy(update={"content": sync_out}),
            hit=False,
            saved_ms=0.0,
        )
    return _with_spec_flags(cascade_resp, hit=False, saved_ms=0.0)


def _hit(
    engine: SpeculativeEngine,
    cascade_resp: ChatResponse,
    tool_output: str,
    saved_ms: float,
    *,
    tool_call: ToolPrediction | None = None,
) -> ChatResponse:
    engine._metrics.inc(_METRIC_HIT)
    if saved_ms > 0:
        engine._metrics.inc(_METRIC_SAVED, float(saved_ms))
    engine.record_debug(
        {
            "event": "hit",
            "tool": getattr(tool_call, "tool_name", ""),
            "args": dict(getattr(tool_call, "args", None) or {}),
            "saved_ms": float(saved_ms),
        }
    )
    return _with_spec_flags(
        cascade_resp.model_copy(update={"content": tool_output}),
        hit=True,
        saved_ms=saved_ms,
    )


async def _sync_execute(
    engine: SpeculativeEngine, tool_call: ToolPrediction
) -> str | None:
    """Normal path: one MCP execute through SpeculativeExecutor (public API)."""
    try:
        task = await engine._executor.speculate(tool_call)
        return await asyncio.wait_for(
            engine._executor.await_result(task, task.key),
            timeout=engine._tool_timeout_s,
        )
    except Exception:  # noqa: BLE001
        return None


def _threshold_from_env() -> float:
    raw = os.getenv("NSA_TOOL_SPEC_THRESHOLD", str(_DEFAULT_THRESHOLD))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_THRESHOLD


def _messages_as_dicts(request: ChatRequest) -> list[dict]:
    out: list[dict] = []
    for msg in request.messages or []:
        if hasattr(msg, "model_dump"):
            out.append(msg.model_dump())
        elif isinstance(msg, dict):
            out.append(dict(msg))
        else:
            out.append({"role": getattr(msg, "role", "user"), "content": str(getattr(msg, "content", ""))})
    return out


def _extract_tool_call(resp: ChatResponse) -> ToolPrediction | None:
    tcs = list(getattr(resp, "tool_calls", None) or [])
    if not tcs:
        return None
    entry = tcs[0]
    if not isinstance(entry, dict):
        return None
    fn = entry.get("function") if isinstance(entry.get("function"), dict) else entry
    if not isinstance(fn, dict):
        return None
    name = fn.get("name") or entry.get("name") or entry.get("tool_name")
    if not name:
        return None
    args = fn.get("arguments") if "arguments" in fn else fn.get("args")
    if isinstance(args, str):
        try:
            parsed = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            parsed = {"_raw": args}
        args = parsed if isinstance(parsed, dict) else {"value": parsed}
    elif not isinstance(args, dict):
        args = {}
    return ToolPrediction(tool_name=str(name), args=dict(args), confidence=1.0)


def _with_spec_flags(
    resp: ChatResponse, *, hit: bool, saved_ms: float
) -> ChatResponse:
    metrics = dict(getattr(resp, "metrics", None) or {})
    metrics["cache_hit"] = 1.0 if hit else 0.0
    metrics["speculative_hit"] = 1.0 if hit else 0.0
    metrics["speculative_latency_saved_ms"] = float(saved_ms)
    return resp.model_copy(
        update={
            "speculative_hit": bool(hit),
            "speculative_latency_saved_ms": float(saved_ms),
            "metrics": metrics,
        }
    )


def _task_result(task: SpeculativeTask) -> str | None:
    if task.future.cancelled():
        return None
    exc = task.future.exception() if task.future.done() else None
    if exc is not None:
        return None
    try:
        return task.future.result()
    except Exception:  # noqa: BLE001
        return None


def _latency_saved_ms(task: SpeculativeTask, emit_at: float) -> float:
    started = float(task.started_at)
    finished = float(task.finished_at) if task.finished_at is not None else emit_at
    # Overlap between speculative MCP window and cascade emit.
    overlap = min(finished, emit_at) - started
    return max(0.0, overlap * 1000.0)


def _cancel_all(
    engine: SpeculativeEngine, tasks: dict[str, SpeculativeTask]
) -> None:
    for task in list(tasks.values()):
        try:
            engine._executor.cancel(task)
        except Exception:  # noqa: BLE001
            pass
    tasks.clear()


async def _drain_specs(
    tasks: dict[str, SpeculativeTask], *, timeout_s: float = 2.0
) -> None:
    """Await in-flight speculative futures briefly so MCP results can cache."""
    futs = [t.future for t in tasks.values() if not t.future.done()]
    if not futs:
        return
    try:
        await asyncio.wait(futs, timeout=max(0.05, float(timeout_s)))
    except Exception:  # noqa: BLE001
        pass


async def _cancel_task(task: asyncio.Task[Any]) -> None:
    if task.done():
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass


async def _await_quiet(task: asyncio.Task[Any]) -> None:
    try:
        await task
    except Exception:  # noqa: BLE001
        pass


def empty_chat_response(
    *,
    content: str = "",
    model: str = "cascade",
    tier_used: int = 2,
    thinking_token_cap: int = 256,
    tool_calls: list[dict[str, object]] | None = None,
) -> ChatResponse:
    """Helper for fakes/tests — full ChatResponse with safe defaults."""
    msg = Message(role="assistant", content=content)
    return ChatResponse(
        model=model,
        tier_used=tier_used,
        content=content,
        choices=[ChatChoice(message=msg, finish_reason="tool_calls" if tool_calls else "stop")],
        usage=ChatUsage(),
        thinking_token_cap=thinking_token_cap,
        tool_calls=list(tool_calls or []),
    )
