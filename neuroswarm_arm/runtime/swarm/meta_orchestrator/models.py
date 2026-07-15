"""Pydantic models for Meta Orchestrator coordination state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._utils import new_id, utc_now
from .workflow_state import WorkflowStatus


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class BudgetSlice(_Base):
    """Budget fragment attached to a single node assignment (coordination only)."""

    max_cost_usd: float | None = None
    max_latency_ms: float | None = None
    max_tokens: float | None = None
    max_memory_bytes: int | None = None
    remaining: dict[str, float | None] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentAssignment(_Base):
    """Candidate agent binding for a node — not a schedule slot."""

    node_id: str
    agent_id: str
    agent_type: str = ""
    score: float = 0.0
    candidates: list[str] = Field(default_factory=list)
    budget: BudgetSlice = Field(default_factory=BudgetSlice)
    capabilities: list[str] = Field(default_factory=list)
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    assigned_at: datetime = Field(default_factory=utc_now)


class NodeResult(_Base):
    """Result payload observed from HAOE (coordination view only)."""

    node_id: str
    success: bool = True
    output: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    budget_used: dict[str, float] = Field(default_factory=dict)
    tool_outputs: dict[str, Any] = Field(default_factory=dict)
    memory_refs: list[str] = Field(default_factory=list)
    error: str | None = None
    agent_id: str | None = None
    duration_ms: float = 0.0


class AggregatedResult(_Base):
    """Merged outputs from one or more node results."""

    outputs: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    budgets: dict[str, float] = Field(default_factory=dict)
    tool_outputs: dict[str, Any] = Field(default_factory=dict)
    memory_refs: list[str] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)
    metadata_extra: dict[str, Any] = Field(default_factory=dict)


class ExecutionRequest(_Base):
    """Request handed to HAOE via IHaoeExecutionPort — scheduling stays in HAOE."""

    request_id: str = Field(default_factory=lambda: new_id("req_"))
    execution_id: str
    workflow_id: str
    node_id: str
    agent_id: str
    agent_type: str = ""
    context_ref: str | None = None
    context_payload: dict[str, Any] = Field(default_factory=dict)
    budget: BudgetSlice = Field(default_factory=BudgetSlice)
    correlation: dict[str, str] = Field(default_factory=dict)
    graph_id: str = ""
    priority: int = 2
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionSignal(_Base):
    """Completion / failure / cancel signal observed from HAOE."""

    request_id: str
    execution_id: str
    node_id: str
    status: str  # succeeded | failed | cancelled | timed_out | checkpointed
    result: NodeResult | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetryDecision(_Base):
    """Coordination decision to request a retry (engine lives elsewhere)."""

    node_id: str
    attempt: int = 1
    max_attempts: int = 3
    reason: str = ""
    fallback_agent_id: str | None = None
    skip: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class RollbackPlan(_Base):
    """Rollback notification payload — no durable undo here."""

    execution_id: str
    target_nodes: list[str] = Field(default_factory=list)
    checkpoint_reference: str | None = None
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CheckpointHandle(_Base):
    """Checkpoint coordination handle."""

    checkpoint_id: str
    execution_id: str
    snapshot_ref: str | None = None
    completed_nodes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ProgressSnapshot(_Base):
    """Point-in-time workflow progress."""

    execution_id: str
    status: WorkflowStatus
    completed_nodes: list[str] = Field(default_factory=list)
    pending_nodes: list[str] = Field(default_factory=list)
    ready_nodes: list[str] = Field(default_factory=list)
    running_nodes: list[str] = Field(default_factory=list)
    failed_nodes: list[str] = Field(default_factory=list)
    elapsed_ms: float = 0.0
    estimated_completion_ms: float | None = None
    health: float = 1.0
    parallelism: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowMetrics(_Base):
    """Per-execution metric bag."""

    workflow_latency_ms: float = 0.0
    coordination_latency_ms: float = 0.0
    agent_utilization: float = 0.0
    parallelism: float = 0.0
    barrier_wait_ms: float = 0.0
    aggregation_ms: float = 0.0
    failure_rate: float = 0.0
    retry_requests: int = 0
    checkpoint_count: int = 0
    nodes_completed: int = 0
    nodes_failed: int = 0
    custom: dict[str, float] = Field(default_factory=dict)


class WorkflowExecution(_Base):
    """Canonical workflow coordination record."""

    workflow_id: str = Field(default_factory=lambda: new_id("wf_"))
    execution_id: str = Field(default_factory=lambda: new_id("ex_"))
    graph: Any = None  # TaskGraph or serializable dict
    graph_id: str = ""
    context: Any = None  # SwarmContext or dict handle
    context_id: str | None = None
    assigned_agents: dict[str, AgentAssignment] = Field(default_factory=dict)
    current_nodes: list[str] = Field(default_factory=list)
    completed_nodes: list[str] = Field(default_factory=list)
    failed_nodes: list[str] = Field(default_factory=list)
    pending_nodes: list[str] = Field(default_factory=list)
    ready_nodes: list[str] = Field(default_factory=list)
    skipped_nodes: list[str] = Field(default_factory=list)
    node_results: dict[str, NodeResult] = Field(default_factory=dict)
    aggregated: AggregatedResult = Field(default_factory=AggregatedResult)
    metrics: WorkflowMetrics = Field(default_factory=WorkflowMetrics)
    events: list[dict[str, Any]] = Field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.CREATED
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    checkpoint_reference: str | None = None
    agent_pool: list[str] = Field(default_factory=list)
    correlation: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    cancel_requested: bool = False

    @field_validator("status", mode="before")
    @classmethod
    def _status_coerce(cls, v: Any) -> Any:
        if isinstance(v, str):
            return WorkflowStatus(v)
        return v

    def touch(self) -> None:
        self.updated_at = utc_now()

    def node_set(self) -> set[str]:
        if self.graph is None:
            return set()
        nodes = getattr(self.graph, "nodes", None)
        if isinstance(nodes, dict):
            return set(nodes.keys())
        if isinstance(self.graph, dict):
            gnodes = self.graph.get("nodes", {})
            if isinstance(gnodes, dict):
                return set(gnodes.keys())
        return set()
