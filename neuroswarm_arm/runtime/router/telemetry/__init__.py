"""OpenTelemetry spans for router operations."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping

# Dual GenAI attrs: legacy gen_ai.system + newer gen_ai.provider.name (semconv Development).
GEN_AI_SYSTEM = "neuroswarm"
GEN_AI_PROVIDER = "neuroswarm"


def gen_ai_attrs(*, operation: str = "route") -> dict[str, str]:
    return {
        "gen_ai.system": GEN_AI_SYSTEM,
        "gen_ai.provider.name": GEN_AI_PROVIDER,
        "gen_ai.operation.name": operation,
    }


def mcp_span_attrs(
    *,
    method: str,
    session_id: str,
    protocol_version: str,
) -> dict[str, str]:
    return {
        **gen_ai_attrs(operation="mcp_tools_call"),
        "mcp.method.name": method,
        "mcp.session.id": session_id,
        "mcp.protocol.version": protocol_version,
    }


class RouterTelemetry:
    def __init__(self, *, enabled: bool = False, endpoint: str = "") -> None:
        self.enabled = bool(enabled and endpoint)
        self.endpoint = endpoint
        self._tracer = None
        if self.enabled:
            self._try_init()

    def _try_init(self) -> None:
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            resource = Resource.create({"service.name": "nexus-arm-router"})
            provider = TracerProvider(resource=resource)
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

                exporter = OTLPSpanExporter(endpoint=self.endpoint)
                provider.add_span_processor(BatchSpanProcessor(exporter))
            except Exception:
                pass
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer("router")
        except Exception:
            self.enabled = False
            self._tracer = None

    @contextmanager
    def span(self, name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[Any]:
        if not self.enabled or self._tracer is None:
            yield None
            return
        with self._tracer.start_as_current_span(name, attributes=dict(attributes or {})) as span:
            yield span
