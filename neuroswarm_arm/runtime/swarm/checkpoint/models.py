"""Shared Pydantic models and enums for Checkpoint Manager."""

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


class CheckpointLevel(str, Enum):
    """Granularity / trigger class for a recovery point."""

    WORKFLOW = "workflow"
    SUBGRAPH = "subgraph"
    NODE = "node"
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    PERIODIC = "periodic"
    BARRIER = "barrier"
    DISTRIBUTED_FUTURE = "distributed_future"


class CheckpointStatus(str, Enum):
    """Lifecycle of a durable checkpoint envelope (not execution status)."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    EXPIRED = "expired"
    COMPACTED = "compacted"


class RecoveryStrategy(str, Enum):
    """Deterministic recovery strategies (planning only)."""

    RESUME_CHECKPOINT = "resume_checkpoint"
    RESUME_NODE = "resume_node"
    RESUME_SUBGRAPH = "resume_subgraph"
    RESTART_WORKFLOW = "restart_workflow"
    ROLLBACK_NOTIFY = "rollback_notify"


class PolicyKind(str, Enum):
    """Configurable checkpoint trigger policies."""

    ALWAYS = "always"
    EVERY_N_NODES = "every_n_nodes"
    EVERY_N_SECONDS = "every_n_seconds"
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    BEFORE_AGGREGATION = "before_aggregation"
    MANUAL = "manual"
    CUSTOM = "custom"


class ArtifactReference(_Frozen):
    """Reference-only artifact pointer (no binary payloads)."""

    artifact_id: str
    kind: str = "artifact"
    uri: str | None = None
    content_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CheckpointEnvelope(_Frozen):
    """Mutable-lifecycle envelope around an immutable Checkpoint body."""

    checkpoint_id: str
    status: CheckpointStatus = CheckpointStatus.ACTIVE
    recorded_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None
    expired_at: datetime | None = None
    compacted_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FailureContext(_Frozen):
    """Failure description supplied to the recovery planner."""

    workflow_id: str
    execution_id: str
    failed_nodes: list[str] = Field(default_factory=list)
    completed_nodes: list[str] = Field(default_factory=list)
    reason: str = "failure"
    node_id: str | None = None
    subgraph_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowObservation(_Frozen):
    """Lightweight observation used by policy evaluation (no execution)."""

    workflow_id: str
    execution_id: str
    completed_nodes: list[str] = Field(default_factory=list)
    nodes_since_checkpoint: int = 0
    seconds_since_checkpoint: float = 0.0
    event_kind: str = "tick"
    tool_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
