"""Shared Pydantic models and enums for Experience Store."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._utils import utc_now


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class _Frozen(_Base):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=False,
        frozen=True,
    )


class ArtifactKind(str, Enum):
    OUTPUT = "output"
    LOG = "log"
    METRIC = "metric"
    BENCHMARK = "benchmark"
    REPORT = "report"
    FLAMEGRAPH = "flamegraph"
    PERFORMIX = "performix"


class RecordLifecycle(str, Enum):
    RECORDED = "recorded"
    ARCHIVED = "archived"
    EXPORTED = "exported"


class DatasetKind(str, Enum):
    BENCHMARK = "benchmark"
    POLICY = "policy"
    OFFLINE_RL = "offline_rl"
    ANALYTICS = "analytics"


class ExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"
    PARQUET = "parquet"
    YAML = "yaml"
    OTEL = "otel"


class TokenUsage(_Frozen):
    """Token accounting for a completed execution."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0

    @field_validator(
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "reasoning_tokens",
    )
    @classmethod
    def _non_neg(cls, v: int) -> int:
        if v < 0:
            raise ValueError("must be >= 0")
        return v


class BudgetSnapshot(_Frozen):
    """Frozen budget envelope remnant at record time (refs / scalars only)."""

    envelope_id: str | None = None
    max_cost_usd: float | None = None
    max_latency_ms: float | None = None
    max_tokens: int | None = None
    remaining_cost_usd: float | None = None
    remaining_latency_ms: float | None = None
    remaining_tokens: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentAssignment(_Frozen):
    """Agent binding used during an execution."""

    agent_id: str
    agent_type: str | None = None
    role: str | None = None
    node_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCallRef(_Frozen):
    """Reference to a tool invocation (no payloads)."""

    tool_name: str
    call_id: str | None = None
    success: bool = True
    latency_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("latency_ms")
    @classmethod
    def _non_neg_lat(cls, v: float) -> float:
        if v < 0:
            raise ValueError("must be >= 0")
        return v


class CheckpointRef(_Frozen):
    """External checkpoint handle (persistence owned elsewhere)."""

    checkpoint_id: str
    node_id: str | None = None
    kind: str | None = None
    uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResourceUsage(_Frozen):
    """Resource sample attached to an execution."""

    memory_bytes: int = 0
    cpu_percent: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("memory_bytes")
    @classmethod
    def _non_neg_mem(cls, v: int) -> int:
        if v < 0:
            raise ValueError("must be >= 0")
        return v

    @field_validator("cpu_percent")
    @classmethod
    def _non_neg_cpu(cls, v: float) -> float:
        if v < 0:
            raise ValueError("must be >= 0")
        return v


class RecordEnvelope(_Frozen):
    """Lifecycle envelope around an immutable execution body."""

    execution_id: str
    lifecycle: RecordLifecycle = RecordLifecycle.RECORDED
    recorded_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None
    exported_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
