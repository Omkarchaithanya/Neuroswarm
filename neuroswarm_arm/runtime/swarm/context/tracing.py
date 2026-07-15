"""TraceContext — correlation / OpenTelemetry-shaped baggage."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import Field

from .models import _Base


def _hex_id(n: int = 16) -> str:
    return uuid4().hex[:n] if n < 32 else uuid4().hex


class TraceContext(_Base):
    """Distributed-tracing ready correlation IDs (aligns with ROF field names)."""

    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    span_id: str = Field(default_factory=lambda: _hex_id(16))
    parent_span_id: str | None = None
    workflow_id: str = Field(default_factory=lambda: uuid4().hex)
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    correlation_id: str = Field(default_factory=lambda: uuid4().hex)
    agent_id: str = ""
    execution_id: str = Field(default_factory=lambda: uuid4().hex)
    conversation_id: str = ""
    envelope_id: str = ""
    baggage: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def child(self, *, agent_id: str | None = None) -> TraceContext:
        return TraceContext(
            trace_id=self.trace_id,
            span_id=_hex_id(16),
            parent_span_id=self.span_id,
            workflow_id=self.workflow_id,
            request_id=self.request_id,
            correlation_id=self.correlation_id,
            agent_id=agent_id if agent_id is not None else self.agent_id,
            execution_id=uuid4().hex,
            conversation_id=self.conversation_id,
            envelope_id=self.envelope_id,
            baggage=dict(self.baggage),
            metadata=dict(self.metadata),
        )

    def to_otel_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "nexus.trace_id": self.trace_id,
            "nexus.span_id": self.span_id,
            "nexus.parent_span_id": self.parent_span_id or "",
            "nexus.workflow_id": self.workflow_id,
            "nexus.request_id": self.request_id,
            "nexus.correlation_id": self.correlation_id,
            "nexus.agent_id": self.agent_id,
            "nexus.execution_id": self.execution_id,
            "nexus.conversation_id": self.conversation_id,
            "nexus.envelope_id": self.envelope_id,
        }
        for k, v in self.baggage.items():
            attrs[f"nexus.baggage.{k}"] = v
        return {k: v for k, v in attrs.items() if v != "" and v is not None}

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")
