"""Immutable RuntimeTraceContext — AsyncIO-safe via contextvars."""

from __future__ import annotations

import threading
from contextvars import ContextVar, Token
from typing import Any, Mapping
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _hex_id(n: int = 16) -> str:
    return uuid4().hex[:n] if n < 32 else uuid4().hex


class RuntimeTraceContext(BaseModel):
    """Immutable per-request observability context.

    Mutate only via evolve() — never in-place.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    span_id: str = Field(default_factory=lambda: _hex_id(16))
    parent_span_id: str = ""
    workflow_id: str = Field(default_factory=lambda: uuid4().hex)
    execution_id: str = Field(default_factory=lambda: uuid4().hex)
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    agent_id: str = ""
    conversation_id: str = ""
    planner_id: str = ""
    decision_id: str = ""
    budget_id: str = ""
    envelope_id: str = ""
    backend_id: str = ""
    model_id: str = ""
    quantization: str = ""
    worker_id: str = ""
    thread_id: str = Field(default_factory=lambda: str(threading.get_ident()))
    numa_node: int | None = None
    hardware_id: str = ""
    telemetry_metadata: Mapping[str, str] = Field(default_factory=dict)
    correlation_ids: Mapping[str, str] = Field(default_factory=dict)

    def evolve(self, **fields: Any) -> RuntimeTraceContext:
        data = self.model_dump()
        data.update({k: v for k, v in fields.items() if v is not None})
        return RuntimeTraceContext.model_validate(data)

    def child_span(self, **fields: Any) -> RuntimeTraceContext:
        return self.evolve(
            parent_span_id=self.span_id,
            span_id=_hex_id(16),
            execution_id=uuid4().hex,
            **fields,
        )

    def to_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "nexus.trace_id": self.trace_id,
            "nexus.span_id": self.span_id,
            "nexus.parent_span_id": self.parent_span_id,
            "nexus.workflow_id": self.workflow_id,
            "nexus.execution_id": self.execution_id,
            "nexus.request_id": self.request_id,
            "nexus.agent_id": self.agent_id,
            "nexus.conversation_id": self.conversation_id,
            "nexus.planner_id": self.planner_id,
            "nexus.decision_id": self.decision_id,
            "nexus.budget_id": self.budget_id,
            "nexus.envelope_id": self.envelope_id,
            "nexus.backend_id": self.backend_id,
            "nexus.model_id": self.model_id,
            "nexus.quantization": self.quantization,
            "nexus.worker_id": self.worker_id,
            "nexus.thread_id": self.thread_id,
            "nexus.hardware_id": self.hardware_id,
        }
        if self.numa_node is not None:
            attrs["nexus.numa_node"] = self.numa_node
        for k, v in self.telemetry_metadata.items():
            attrs[f"nexus.meta.{k}"] = v
        for k, v in self.correlation_ids.items():
            attrs[f"nexus.corr.{k}"] = v
        return {k: v for k, v in attrs.items() if v != "" and v is not None}

    def to_otel_baggage(self) -> dict[str, str]:
        bag = {
            "nexus.request_id": self.request_id,
            "nexus.execution_id": self.execution_id,
            "nexus.workflow_id": self.workflow_id,
            "nexus.agent_id": self.agent_id,
            "nexus.envelope_id": self.envelope_id,
            "nexus.conversation_id": self.conversation_id,
            "nexus.budget_id": self.budget_id,
            "nexus.planner_id": self.planner_id,
            "nexus.decision_id": self.decision_id,
            "nexus.backend_id": self.backend_id,
            "nexus.model_id": self.model_id,
            "nexus.quantization": self.quantization,
        }
        if self.numa_node is not None:
            bag["nexus.numa_node"] = str(self.numa_node)
        bag.update({f"nexus.meta.{k}": v for k, v in self.telemetry_metadata.items()})
        return {k: v for k, v in bag.items() if v}

    def to_carrier(self) -> dict[str, str]:
        """Custom nexus-runtime carrier for worker pools / streaming."""
        carrier = {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "request_id": self.request_id,
            "agent_id": self.agent_id,
            "conversation_id": self.conversation_id,
            "planner_id": self.planner_id,
            "decision_id": self.decision_id,
            "budget_id": self.budget_id,
            "envelope_id": self.envelope_id,
            "backend_id": self.backend_id,
            "model_id": self.model_id,
            "quantization": self.quantization,
            "worker_id": self.worker_id,
            "thread_id": self.thread_id,
            "hardware_id": self.hardware_id,
        }
        if self.numa_node is not None:
            carrier["numa_node"] = str(self.numa_node)
        return {k: v for k, v in carrier.items() if v != ""}

    @classmethod
    def from_carrier(cls, carrier: Mapping[str, str]) -> RuntimeTraceContext:
        numa_raw = carrier.get("numa_node", "")
        numa: int | None = int(numa_raw) if numa_raw.isdigit() else None
        return cls(
            trace_id=carrier.get("trace_id", "") or uuid4().hex,
            span_id=carrier.get("span_id", "") or _hex_id(16),
            parent_span_id=carrier.get("parent_span_id", ""),
            workflow_id=carrier.get("workflow_id", "") or uuid4().hex,
            execution_id=carrier.get("execution_id", "") or uuid4().hex,
            request_id=carrier.get("request_id", "") or uuid4().hex,
            agent_id=carrier.get("agent_id", ""),
            conversation_id=carrier.get("conversation_id", ""),
            planner_id=carrier.get("planner_id", ""),
            decision_id=carrier.get("decision_id", ""),
            budget_id=carrier.get("budget_id", ""),
            envelope_id=carrier.get("envelope_id", ""),
            backend_id=carrier.get("backend_id", ""),
            model_id=carrier.get("model_id", ""),
            quantization=carrier.get("quantization", ""),
            worker_id=carrier.get("worker_id", ""),
            thread_id=carrier.get("thread_id", "") or str(threading.get_ident()),
            numa_node=numa,
            hardware_id=carrier.get("hardware_id", ""),
        )

    def to_haoe_correlation(self) -> Any:
        from neuroswarm_arm.runtime.haoe.interfaces.types import CorrelationIds

        return CorrelationIds(
            trace_id=self.trace_id,
            workflow_id=self.workflow_id,
            request_id=self.request_id,
            agent_id=self.agent_id,
            execution_id=self.execution_id,
            correlation_id=self.correlation_ids.get("correlation_id", self.request_id),
        )

    @classmethod
    def from_haoe_correlation(cls, ids: Any, **extra: Any) -> RuntimeTraceContext:
        return cls(
            trace_id=getattr(ids, "trace_id", "") or uuid4().hex,
            workflow_id=getattr(ids, "workflow_id", "") or uuid4().hex,
            request_id=getattr(ids, "request_id", "") or uuid4().hex,
            agent_id=getattr(ids, "agent_id", "") or "",
            execution_id=getattr(ids, "execution_id", "") or uuid4().hex,
            correlation_ids={"correlation_id": getattr(ids, "correlation_id", "") or ""},
            **extra,
        )

    @classmethod
    def from_otel_context(cls, baggage: Mapping[str, str] | None = None, **extra: Any) -> RuntimeTraceContext:
        bag = dict(baggage or {})
        return cls(
            request_id=bag.get("nexus.request_id", "") or uuid4().hex,
            execution_id=bag.get("nexus.execution_id", "") or uuid4().hex,
            workflow_id=bag.get("nexus.workflow_id", "") or uuid4().hex,
            agent_id=bag.get("nexus.agent_id", ""),
            envelope_id=bag.get("nexus.envelope_id", ""),
            conversation_id=bag.get("nexus.conversation_id", ""),
            budget_id=bag.get("nexus.budget_id", ""),
            planner_id=bag.get("nexus.planner_id", ""),
            decision_id=bag.get("nexus.decision_id", ""),
            backend_id=bag.get("nexus.backend_id", ""),
            model_id=bag.get("nexus.model_id", ""),
            quantization=bag.get("nexus.quantization", ""),
            numa_node=int(bag["nexus.numa_node"]) if bag.get("nexus.numa_node", "").isdigit() else None,
            **extra,
        )

    def to_log_fields(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "request_id": self.request_id,
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "agent_id": self.agent_id,
            "planner_id": self.planner_id,
            "backend": self.backend_id,
            "model": self.model_id,
            "envelope_id": self.envelope_id,
            "budget_id": self.budget_id,
            "conversation_id": self.conversation_id,
            "quantization": self.quantization,
            "numa_node": self.numa_node,
        }


_CURRENT: ContextVar[RuntimeTraceContext | None] = ContextVar("rof_runtime_trace_context", default=None)


def get_current_context() -> RuntimeTraceContext | None:
    return _CURRENT.get()


def require_context() -> RuntimeTraceContext:
    ctx = _CURRENT.get()
    if ctx is None:
        ctx = RuntimeTraceContext()
        _CURRENT.set(ctx)
    return ctx


def set_current_context(ctx: RuntimeTraceContext) -> Token[RuntimeTraceContext | None]:
    return _CURRENT.set(ctx)


def reset_current_context(token: Token[RuntimeTraceContext | None]) -> None:
    _CURRENT.reset(token)


def clear_current_context() -> None:
    _CURRENT.set(None)
