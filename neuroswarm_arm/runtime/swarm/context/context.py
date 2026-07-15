"""SwarmContext — shared runtime operating state for NEXUS-ARM."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import Field, field_validator

from ._utils import new_id, stable_hash, utc_now
from .budget import BudgetContext
from .execution import ExecutionContext
from .knowledge import KnowledgeContext
from .memory import MemoryContext
from .metrics import ContextMetrics
from .models import (
    ExternalRef,
    HistoryEntry,
    RegistryHandle,
    TaskGraphRef,
    TelemetryContext,
    _Base,
    ContextRefKind,
)
from .request import RequestContext
from .tools import ToolContext
from .tracing import TraceContext
from .versioning import CONTEXT_SCHEMA_VERSION


class SwarmContext(_Base):
    """Context Operating System state delivered to every runtime subsystem.

    Not a dict. Not LangChain memory. Shared process-context analogue for
    Task Graph / Agent Registry / Meta Orchestrator / HAOE / DIPA consumers.
    """

    # ------------------------------------------------------------------ identity
    swarm_id: str = Field(default_factory=lambda: new_id("sw_"))
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    workflow_id: str = Field(default_factory=lambda: uuid4().hex)
    execution_id: str = Field(default_factory=lambda: uuid4().hex)
    session_id: str | None = None
    user_id: str | None = None
    tenant_id: str | None = None
    snapshot_id: str | None = None

    # ------------------------------------------------------------------ domains
    request: RequestContext = Field(default_factory=RequestContext)
    budget: BudgetContext = Field(default_factory=BudgetContext)
    memory: MemoryContext = Field(default_factory=MemoryContext)
    knowledge: KnowledgeContext = Field(default_factory=KnowledgeContext)
    execution: ExecutionContext = Field(default_factory=ExecutionContext)
    tools: ToolContext = Field(default_factory=ToolContext)
    metrics: ContextMetrics = Field(default_factory=ContextMetrics)
    trace_context: TraceContext = Field(default_factory=TraceContext)
    telemetry_context: TelemetryContext = Field(default_factory=TelemetryContext)

    # ------------------------------------------------------------------ refs
    mem0_reference: ExternalRef = Field(
        default_factory=lambda: ExternalRef(kind=ContextRefKind.MEM0)
    )
    okf_reference: ExternalRef = Field(
        default_factory=lambda: ExternalRef(kind=ContextRefKind.OKF)
    )
    knowledge_reference: ExternalRef = Field(
        default_factory=lambda: ExternalRef(kind=ContextRefKind.KNOWLEDGE)
    )
    tool_registry: RegistryHandle = Field(default_factory=RegistryHandle)
    agent_registry: RegistryHandle = Field(default_factory=RegistryHandle)
    task_graph: TaskGraphRef = Field(default_factory=TaskGraphRef)

    # ------------------------------------------------------------------ plan
    execution_plan: dict[str, Any] = Field(default_factory=dict)
    current_node: str | None = None
    current_agent: str | None = None

    # ------------------------------------------------------------------ lifecycle
    checkpoints: list[str] = Field(default_factory=list)
    history: list[HistoryEntry] = Field(default_factory=list)
    version: str = CONTEXT_SCHEMA_VERSION
    schema_version: str = CONTEXT_SCHEMA_VERSION
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    tags: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("version", "schema_version")
    @classmethod
    def _version_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("version must be non-empty")
        return v.strip()

    # ------------------------------------------------------------------ ops
    def touch(self) -> SwarmContext:
        return self.model_copy(update={"updated_at": utc_now()})

    def evolve(self, **fields: Any) -> SwarmContext:
        data = {k: v for k, v in fields.items() if v is not None}
        data["updated_at"] = utc_now()
        return self.model_copy(update=data)

    def clone(self) -> SwarmContext:
        return self.model_copy(deep=True)

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"created_at", "updated_at", "snapshot_id"})
        return stable_hash(payload)

    def append_history(self, event_type: str, summary: str = "", **meta: Any) -> SwarmContext:
        entry = HistoryEntry(
            event_type=event_type,
            timestamp=utc_now().isoformat(),
            summary=summary,
            metadata=meta,
        )
        return self.evolve(history=list(self.history) + [entry])

    def sync_ids_from_trace(self) -> SwarmContext:
        """Align top-level IDs with trace_context when empty / stale."""
        return self.evolve(
            request_id=self.request_id or self.trace_context.request_id,
            workflow_id=self.workflow_id or self.trace_context.workflow_id,
            execution_id=self.execution_id or self.trace_context.execution_id,
            current_node=self.current_node or self.execution.current_node,
            current_agent=self.current_agent or self.execution.current_agent,
        )

    def refresh_metrics(self) -> SwarmContext:
        import json

        raw = json.dumps(self.model_dump(mode="json"), default=str)
        mem_refs = 0
        if not self.memory.mem0_reference.is_empty():
            mem_refs += 1
        if not self.memory.okf_reference.is_empty():
            mem_refs += 1
        if not self.memory.long_term_memory_ref.is_empty():
            mem_refs += 1
        if not self.mem0_reference.is_empty():
            mem_refs += 1
        know_refs = len(self.knowledge.documents) + len(self.knowledge.namespaces)
        rem = self.budget.remaining_cost()
        ratio = 0.0
        if self.budget.cost_usd_limit and self.budget.cost_usd_limit > 0:
            ratio = self.budget.cost_usd_used / self.budget.cost_usd_limit
        m = self.metrics.model_copy(
            update={
                "context_size_bytes": len(raw.encode("utf-8")),
                "memory_ref_count": mem_refs,
                "knowledge_ref_count": know_refs,
                "budget_usage_ratio": ratio,
                "execution_depth": self.execution.depth,
            }
        )
        return self.evolve(metrics=m)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")

    def as_condition_map(self) -> dict[str, Any]:
        """Flat map for Task Graph condition evaluation (legacy-compatible keys)."""
        return {
            "swarm": self.to_dict(),
            "confidence": self.execution.confidence,
            "budget": self.budget.to_dict(),
            "latency_ms_used": self.budget.latency_ms_used,
            "memory_pressure": self.memory.memory_pressure,
            "available_tools": set(self.tools.available_tools or self.execution.available_tools),
            "available_models": set(self.execution.available_models),
            "node_results": self.execution.node_results or self.extra.get("node_results", {}),
            "node_statuses": self.execution.node_statuses or self.extra.get("node_statuses", {}),
            **self.extra,
        }
