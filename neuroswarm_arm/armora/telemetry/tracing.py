"""ROF tracing — OpenTelemetry-backed spans with local SpanRecord fan-out."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping

from .context import (
    RuntimeTraceContext,
    get_current_context,
    require_context,
    reset_current_context,
    set_current_context,
)
from .schemas import SpanRecord


@dataclass
class _ActiveSpan:
    name: str
    span_id: str
    trace_id: str
    parent_span_id: str
    start_ns: int
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "unset"
    otel_span: Any = None
    sampled: bool = True


class ROFTracer:
    """Starts spans bound to RuntimeTraceContext; exports via lifecycle queue."""

    def __init__(
        self,
        *,
        sampler: Any,
        on_span_end: Any | None = None,
        tracer_name: str = "nexus.armora.rof",
        enabled: bool = True,
    ) -> None:
        self.sampler = sampler
        self.on_span_end = on_span_end
        self.tracer_name = tracer_name
        self.enabled = enabled
        self._otel_tracer = None
        if enabled:
            self._try_init_otel()

    def _try_init_otel(self) -> None:
        try:
            from opentelemetry import trace

            self._otel_tracer = trace.get_tracer(self.tracer.tracer_name if False else self.tracer_name)
        except Exception:
            self._otel_tracer = None

    def bind_otel_tracer(self, tracer: Any) -> None:
        self._otel_tracer = tracer

    @contextmanager
    def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, Any] | None = None,
        parent: Any | None = None,
    ) -> Iterator[_ActiveSpan]:
        del parent
        ctx = require_context()
        attrs = dict(attributes or {})
        attrs.update(ctx.to_attributes())
        decision = self.sampler.should_sample(name=name, attributes=attrs)
        child = ctx.child_span()
        token = set_current_context(child)
        start_ns = time.time_ns()
        otel_cm = None
        otel_span = None
        if decision.sampled and self._otel_tracer is not None:
            try:
                otel_cm = self._otel_tracer.start_as_current_span(name, attributes=_otel_attrs(attrs))
                otel_span = otel_cm.__enter__()
            except Exception:
                otel_cm = None
                otel_span = None
        active = _ActiveSpan(
            name=name,
            span_id=child.span_id,
            trace_id=child.trace_id,
            parent_span_id=child.parent_span_id,
            start_ns=start_ns,
            attributes=attrs,
            otel_span=otel_span,
            sampled=decision.sampled,
        )
        try:
            yield active
            active.status = "ok"
        except Exception as exc:
            active.status = "error"
            active.attributes["nexus.error"] = str(exc)[:256]
            active.attributes["nexus.outcome"] = "error"
            if otel_span is not None:
                try:
                    from opentelemetry.trace import Status, StatusCode

                    otel_span.set_status(Status(StatusCode.ERROR, str(exc)[:128]))
                    otel_span.record_exception(exc)
                except Exception:
                    pass
            raise
        finally:
            end_ns = time.time_ns()
            if otel_cm is not None:
                try:
                    otel_cm.__exit__(None, None, None)
                except Exception:
                    pass
            record = SpanRecord(
                span_id=active.span_id,
                trace_id=active.trace_id,
                parent_span_id=active.parent_span_id,
                name=active.name,
                start_ns=active.start_ns,
                end_ns=end_ns,
                status=active.status,
                attributes=dict(active.attributes),
            )
            if active.sampled and self.on_span_end is not None:
                try:
                    self.on_span_end(record)
                except Exception:
                    pass
            reset_current_context(token)

    @contextmanager
    def start_request(
        self,
        *,
        request_id: str = "",
        agent_id: str = "",
        workflow_id: str = "",
        attributes: Mapping[str, Any] | None = None,
        name: str = "nexus.armora.request",
    ) -> Iterator[tuple[RuntimeTraceContext, _ActiveSpan]]:
        root = RuntimeTraceContext(
            request_id=request_id or RuntimeTraceContext().request_id,
            agent_id=agent_id,
            workflow_id=workflow_id or RuntimeTraceContext().workflow_id,
        )
        token = set_current_context(root)
        try:
            with self.start_span(name, attributes=attributes) as span:
                yield get_current_context() or root, span
        finally:
            reset_current_context(token)


def _otel_attrs(attrs: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in attrs.items():
        if isinstance(v, (str, bool, int, float)):
            out[k] = v
        elif v is None:
            continue
        else:
            out[k] = str(v)[:256]
    return out
