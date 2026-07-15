"""Shared Pydantic models and enums for Rollback Manager."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._utils import utc_now


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class _Frozen(_Base):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=False,
        frozen=True,
    )


class RollbackLevel(str, Enum):
    """Granularity of a rollback operation."""

    WORKFLOW = "workflow"
    SUBGRAPH = "subgraph"
    NODE = "node"
    CONTEXT = "context"
    BUDGET = "budget"
    EXECUTION_METADATA = "execution_metadata"
    DISTRIBUTED_FUTURE = "distributed_future"


class RollbackStrategyKind(str, Enum):
    """Deterministic rollback strategies (planning only — pure objects)."""

    RESUME_CHECKPOINT = "resume_checkpoint"
    RESTART_WORKFLOW = "restart_workflow"
    RESTART_NODE = "restart_node"
    RESTART_SUBGRAPH = "restart_subgraph"
    ROLLBACK_CONTEXT = "rollback_context"
    ROLLBACK_BUDGET = "rollback_budget"
    ROLLBACK_METADATA = "rollback_metadata"
    CUSTOM = "custom"


class RollbackStatus(str, Enum):
    """Lifecycle of a rollback operation envelope."""

    PENDING = "pending"
    VALIDATED = "validated"
    PREPARED = "prepared"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PolicyKind(str, Enum):
    """Configurable rollback trigger policies."""

    ALWAYS = "always"
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    THRESHOLD = "threshold"
    BUDGET = "budget"
    LATENCY = "latency"
    FAILURE = "failure"
    CUSTOM = "custom"


class InitiatorKind(str, Enum):
    """Who / what initiated the rollback."""

    SYSTEM = "system"
    OPERATOR = "operator"
    POLICY = "policy"
    COORDINATOR = "coordinator"
    CUSTOM = "custom"


class ConsistencyViolationKind(str, Enum):
    """Detected consistency violation classes."""

    ORPHAN_NODE = "orphan_node"
    INVALID_CHECKPOINT = "invalid_checkpoint"
    VERSION_MISMATCH = "version_mismatch"
    PARTIAL_FAILURE = "partial_failure"
    CONTEXT_INCONSISTENT = "context_inconsistent"
    BUDGET_INCONSISTENT = "budget_inconsistent"
    ARTIFACT_DANGLING = "artifact_dangling"
    EXPERIENCE_DANGLING = "experience_dangling"
    GRAPH_INCONSISTENT = "graph_inconsistent"
    EXECUTION_INCONSISTENT = "execution_inconsistent"
    METADATA_INCONSISTENT = "metadata_inconsistent"


class ArtifactReference(_Frozen):
    """Reference-only artifact pointer (no binary payloads)."""

    artifact_id: str
    kind: str = "artifact"
    uri: str | None = None
    content_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConsistencyViolation(_Frozen):
    """Single consistency violation finding."""

    kind: ConsistencyViolationKind
    message: str
    path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConsistencyReport(_Frozen):
    """Result of consistency validation."""

    ok: bool = True
    violations: list[ConsistencyViolation] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def violation_count(self) -> int:
        return len(self.violations)


class FailureObservation(_Frozen):
    """Lightweight failure observation for planning / policy (no execution)."""

    workflow_id: str
    execution_id: str
    failed_nodes: list[str] = Field(default_factory=list)
    completed_nodes: list[str] = Field(default_factory=list)
    reason: str = "failure"
    node_id: str | None = None
    subgraph_id: str | None = None
    context_id: str | None = None
    budget_envelope_id: str | None = None
    checkpoint_reference: str | None = None
    recovery_plan_reference: str | None = None
    latency_ms: float | None = None
    budget_remaining: float | None = None
    failure_count: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class RollbackObservation(_Frozen):
    """Observation used by policy evaluation (no execution)."""

    workflow_id: str
    execution_id: str
    failure_count: int = 0
    latency_ms: float = 0.0
    budget_remaining: float | None = None
    threshold: float | None = None
    event_kind: str = "failure"
    manual: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class RollbackAnalytics(_Frozen):
    """Aggregate analytics for rollback history (no execution logs)."""

    execution_id: str | None = None
    workflow_id: str | None = None
    total_rollbacks: int = 0
    success_count: int = 0
    failure_count: int = 0
    cancelled_count: int = 0
    strategy_usage: dict[str, int] = Field(default_factory=dict)
    mean_duration_ms: float = 0.0
    consistency_violations: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
