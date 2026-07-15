"""Immutable ExecutionRecord — historical unit of completed runtime work."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator, model_validator

from ._utils import new_id, stable_hash, utc_now
from .artifacts import ArtifactRef
from .models import (
    AgentAssignment,
    BudgetSnapshot,
    CheckpointRef,
    ResourceUsage,
    TokenUsage,
    ToolCallRef,
    _Frozen,
)
from .quality import QualityScore


class ExecutionRecord(_Frozen):
    """Append-only historical record of one completed workflow execution.

    Not a logger, conversation history, or mutable DB row. Consumers (GEPA,
    benchmarking, policy evolution, offline RL, dashboards) read this after
    execution finishes.
    """

    execution_id: str = Field(default_factory=lambda: new_id("exec_"))
    workflow_id: str
    request_id: str | None = None
    session_id: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)

    task_graph_reference: str | None = None
    execution_plan_reference: str | None = None

    agent_assignments: list[AgentAssignment] = Field(default_factory=list)
    models_used: list[str] = Field(default_factory=list)
    backends_used: list[str] = Field(default_factory=list)
    quantizations: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallRef] = Field(default_factory=list)

    latency: float = 0.0
    queue_latency: float = 0.0
    execution_latency: float = 0.0

    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    reasoning_tokens: int = 0
    memory_usage: ResourceUsage = Field(default_factory=ResourceUsage)
    cpu_usage: float = 0.0
    estimated_energy: float = 0.0
    estimated_cost: float = 0.0
    budget: BudgetSnapshot | None = None

    quality_score: QualityScore = Field(default_factory=QualityScore)
    success: bool = True
    failure_reason: str | None = None
    retry_count: int = 0

    checkpoints: list[CheckpointRef] = Field(default_factory=list)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)

    telemetry_reference: str | None = None
    trace_reference: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    version: int = 1
    content_hash: str | None = None

    @field_validator(
        "latency",
        "queue_latency",
        "execution_latency",
        "cpu_usage",
        "estimated_energy",
        "estimated_cost",
    )
    @classmethod
    def _non_neg_float(cls, v: float) -> float:
        if v < 0:
            raise ValueError("must be >= 0")
        return v

    @field_validator("reasoning_tokens", "retry_count", "version")
    @classmethod
    def _non_neg_int(cls, v: int) -> int:
        if v < 0:
            raise ValueError("must be >= 0")
        return v

    @field_validator("workflow_id")
    @classmethod
    def _workflow_required(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("workflow_id must be non-empty")
        return str(v).strip()

    @model_validator(mode="after")
    def _consistency(self) -> ExecutionRecord:
        if not self.success and not self.failure_reason:
            object.__setattr__(
                self, "failure_reason", "unspecified_failure"
            )
        if self.reasoning_tokens == 0 and self.token_usage.reasoning_tokens:
            object.__setattr__(
                self, "reasoning_tokens", self.token_usage.reasoning_tokens
            )
        if not self.content_hash:
            payload = self.model_dump(mode="json", exclude={"content_hash"})
            object.__setattr__(self, "content_hash", stable_hash(payload))
        return self

    def rehash(self) -> str:
        """Compute content hash from current fields (read-only helper)."""
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        return stable_hash(payload)
