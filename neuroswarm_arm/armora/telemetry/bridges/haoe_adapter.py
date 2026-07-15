"""HAOE adapter — CorrelationIds ↔ RuntimeTraceContext; use shared tracer."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from ..context import RuntimeTraceContext, get_current_context, set_current_context
from ..schemas import SpanNames


class HAOEObservabilityAdapter:
    """Injected into HAOE so it does not own TracerProvider."""

    def __init__(self, rof: Any) -> None:
        self.rof = rof

    def bind_ids(self, ids: Any) -> RuntimeTraceContext:
        ctx = RuntimeTraceContext.from_haoe_correlation(ids)
        current = get_current_context()
        if current is not None:
            ctx = current.evolve(
                trace_id=current.trace_id or ctx.trace_id,
                workflow_id=ctx.workflow_id or current.workflow_id,
                request_id=ctx.request_id or current.request_id,
                agent_id=ctx.agent_id or current.agent_id,
                execution_id=ctx.execution_id,
                correlation_ids=ctx.correlation_ids,
            )
        set_current_context(ctx)
        return ctx

    @contextmanager
    def workflow_span(self, ids: Any, *, attributes: Mapping[str, Any] | None = None) -> Iterator[Any]:
        self.bind_ids(ids)
        with self.rof.span(SpanNames.HAOE_WORKFLOW, attributes=attributes) as span:
            yield span

    @contextmanager
    def task_span(self, name: str, ids: Any, *, attributes: Mapping[str, Any] | None = None) -> Iterator[Any]:
        self.bind_ids(ids)
        attrs = dict(attributes or {})
        attrs["nexus.task_name"] = name
        with self.rof.span(SpanNames.HAOE_TASK, attributes=attrs) as span:
            yield span
