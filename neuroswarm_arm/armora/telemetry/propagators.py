"""Context propagation — AsyncIO, worker pools, streaming carriers."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from functools import wraps
from typing import Any, Callable, Iterator, Mapping, TypeVar

from .context import (
    RuntimeTraceContext,
    clear_current_context,
    get_current_context,
    reset_current_context,
    set_current_context,
)

T = TypeVar("T")
R = TypeVar("R")


def inject(carrier: dict[str, str] | None = None) -> dict[str, str]:
    ctx = get_current_context()
    out = dict(carrier or {})
    if ctx is None:
        return out
    out.update(ctx.to_carrier())
    try:
        from opentelemetry.propagate import inject as otel_inject

        otel_inject(out)
    except Exception:
        pass
    return out


def extract(carrier: Mapping[str, str]) -> RuntimeTraceContext:
    ctx = RuntimeTraceContext.from_carrier(carrier)
    try:
        from opentelemetry.propagate import extract as otel_extract
        from opentelemetry import context as otel_context
        from opentelemetry import baggage

        otel_ctx = otel_extract(dict(carrier))
        bag: dict[str, str] = {}
        for key in (
            "nexus.request_id",
            "nexus.execution_id",
            "nexus.workflow_id",
            "nexus.agent_id",
            "nexus.envelope_id",
        ):
            val = baggage.get_baggage(key, context=otel_ctx)
            if val:
                bag[key] = str(val)
        if bag:
            ctx = RuntimeTraceContext.from_otel_context(bag).evolve(
                trace_id=ctx.trace_id,
                span_id=ctx.span_id,
                parent_span_id=ctx.parent_span_id,
            )
        otel_context.attach(otel_ctx)
    except Exception:
        pass
    return ctx


def attach(ctx: RuntimeTraceContext) -> Any:
    return set_current_context(ctx)


def detach(token: Any) -> None:
    reset_current_context(token)


def propagate_async(coro_fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: capture context and restore inside async coroutine."""

    @wraps(coro_fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        carrier = inject()
        ctx = extract(carrier)
        token = set_current_context(ctx)
        try:
            return await coro_fn(*args, **kwargs)
        finally:
            reset_current_context(token)

    return wrapper


def run_in_executor_with_context(
    loop: asyncio.AbstractEventLoop,
    executor: Any,
    fn: Callable[..., R],
    *args: Any,
) -> Future[R]:  # type: ignore[type-arg]
    carrier = inject()

    def _wrapped() -> R:
        ctx = extract(carrier)
        token = set_current_context(ctx)
        try:
            return fn(*args)
        finally:
            reset_current_context(token)

    return loop.run_in_executor(executor, _wrapped)  # type: ignore[return-value]


def wrap_streaming(iterator: Iterator[T]) -> Iterator[T]:
    """Propagate current context across streaming iterator ticks."""
    carrier = inject()

    def _gen() -> Iterator[T]:
        ctx = extract(carrier)
        token = set_current_context(ctx)
        try:
            for item in iterator:
                yield item
        finally:
            reset_current_context(token)

    return _gen()


def snapshot_context() -> RuntimeTraceContext | None:
    return get_current_context()


def clear() -> None:
    clear_current_context()
