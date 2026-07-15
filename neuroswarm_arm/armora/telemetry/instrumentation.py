"""Instrumentation helpers for Gateway, Budget, HAOE, DIPA."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from .context import RuntimeTraceContext, get_current_context, set_current_context
from .schemas import EventType, SpanNames
from .spans import decision_attributes


@contextmanager
def instrument_stage(
    rof: Any,
    name: str,
    *,
    attributes: Mapping[str, Any] | None = None,
    event_start: EventType | None = None,
    event_end: EventType | None = None,
    histogram: str | None = None,
) -> Iterator[Any]:
    """Generic stage instrumentation with optional events + duration histogram."""
    if rof is None or not getattr(getattr(rof, "config", None), "enabled", False):
        yield None
        return
    if event_start is not None:
        rof.emit_builtin(event_start, payload=dict(attributes or {}))
    t0 = time.perf_counter()
    try:
        with rof.span(name, attributes=attributes) as span:
            yield span
        if event_end is not None:
            rof.emit_builtin(event_end, payload=dict(attributes or {}))
    finally:
        if histogram:
            rof.histogram(histogram, time.perf_counter() - t0)


def bind_envelope(rof: Any, envelope_id: str, **extra: Any) -> RuntimeTraceContext | None:
    """Attach budget envelope id to current RuntimeTraceContext."""
    ctx = get_current_context()
    if ctx is None:
        ctx = RuntimeTraceContext(envelope_id=envelope_id, budget_id=envelope_id, **extra)
        set_current_context(ctx)
        return ctx
    evolved = ctx.evolve(envelope_id=envelope_id, budget_id=envelope_id, **extra)
    set_current_context(evolved)
    return evolved


def instrument_gateway_chat(rof: Any, req: Any) -> Any:
    """Context manager factory for gateway chat root."""
    request_id = getattr(req, "request_id", None) or ""
    agent_id = getattr(req, "agent_id", "") or ""
    return rof.start_request(request_id=request_id, agent_id=agent_id, workflow_id="chat")


def instrument_planner(rof: Any, **attrs: Any) -> Any:
    return instrument_stage(
        rof,
        SpanNames.PLANNER,
        attributes=decision_attributes(**attrs),
        event_start=EventType.PLANNER_STARTED,
        event_end=EventType.PLANNER_COMPLETED,
        histogram="nexus_planner_duration_seconds",
    )


def instrument_routing(rof: Any, **attrs: Any) -> Any:
    return instrument_stage(
        rof,
        SpanNames.ROUTING,
        attributes=decision_attributes(**attrs),
        event_start=EventType.ROUTING_STARTED,
        event_end=EventType.ROUTING_COMPLETED,
        histogram="nexus_routing_duration_seconds",
    )


def instrument_infer(rof: Any, **attrs: Any) -> Any:
    return instrument_stage(
        rof,
        SpanNames.DIPA_INFER,
        attributes=decision_attributes(**attrs),
        event_start=EventType.INFERENCE_STARTED,
        event_end=EventType.INFERENCE_FINISHED,
        histogram="nexus_inference_duration_seconds",
    )


def instrument_streaming(rof: Any, **attrs: Any) -> Any:
    return instrument_stage(
        rof,
        SpanNames.STREAMING,
        attributes=decision_attributes(**attrs),
        event_start=EventType.STREAMING_STARTED,
        event_end=EventType.STREAMING_FINISHED,
        histogram="nexus_streaming_duration_seconds",
    )


def bridge_haoe_ids(rof: Any, ids: Any) -> RuntimeTraceContext:
    """Map HAOE CorrelationIds into RuntimeTraceContext."""
    ctx = RuntimeTraceContext.from_haoe_correlation(ids)
    current = get_current_context()
    if current is not None:
        ctx = current.evolve(
            trace_id=ctx.trace_id or current.trace_id,
            workflow_id=ctx.workflow_id or current.workflow_id,
            request_id=ctx.request_id or current.request_id,
            agent_id=ctx.agent_id or current.agent_id,
            execution_id=ctx.execution_id or current.execution_id,
        )
    set_current_context(ctx)
    return ctx
