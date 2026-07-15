"""Shared Pydantic models and enums for RMRE."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._utils import utc_now
from .versioning import SCHEMA_VERSION


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class _Frozen(_Base):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=False,
        frozen=True,
    )


class ModelTier(str, Enum):
    TIER1 = "tier1"
    TIER2 = "tier2"
    TIER3 = "tier3"
    TIER4 = "tier4"
    CUSTOM = "custom"


class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class FallbackDimension(str, Enum):
    MODEL_TIER = "model_tier"
    BACKEND = "backend"
    QUANTIZATION = "quantization"
    CONTEXT_LENGTH = "context_length"
    THREAD_COUNT = "thread_count"
    REASONING_BUDGET = "reasoning_budget"
    TOOL_USAGE = "tool_usage"
    CASCADE = "cascade"


class CascadeStrategy(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL_SCORE = "parallel_score"
    LEAST_DEGRADATION = "least_degradation"


class DecisionKind(str, Enum):
    CONTINUE = "continue"
    TRANSITION = "transition"
    DEGRADE_NOTIFY = "degrade_notify"


class WorkloadHint(str, Enum):
    CHAT = "chat"
    TOOL_CALLING = "tool_calling"
    REASONING = "reasoning"
    CODE = "code"
    EMBEDDING = "embedding"
    GENERAL = "general"


class ModelProfile(_Frozen):
    """Strongly typed model capability / cost / health profile."""

    model_id: str
    family: str = ""
    tier: ModelTier = ModelTier.TIER2
    context_length: int = 8192
    parameter_count: float = 0.0
    quantizations: list[str] = Field(default_factory=lambda: ["Q5_K_M"])
    supported_backends: list[str] = Field(default_factory=lambda: ["llama_cpp"])
    estimated_latency: float = 100.0
    estimated_cost: float = 0.001
    estimated_memory: float = 4.0
    estimated_tokens_per_second: float = 50.0
    preferred_workloads: list[WorkloadHint] = Field(
        default_factory=lambda: [WorkloadHint.GENERAL]
    )
    health: HealthState = HealthState.UNKNOWN
    availability: float = Field(default=1.0, ge=0.0, le=1.0)
    priority: float = Field(default=1.0, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION


class FallbackDimensionConfig(_Frozen):
    """Per-dimension toggle + ordered preference list."""

    dimension: FallbackDimension
    enabled: bool = True
    preferences: list[str] = Field(default_factory=list)
    max_steps: int = 4


class ScoreWeights(_Frozen):
    """Deterministic scoring weights (must sum conceptually; normalized at score time)."""

    quality: float = 0.25
    latency: float = 0.15
    cost: float = 0.10
    memory: float = 0.10
    policy_priority: float = 0.15
    health: float = 0.10
    availability: float = 0.05
    backend_compat: float = 0.05
    budget_fit: float = 0.03
    context_compat: float = 0.02


class RuntimeSignals(_Frozen):
    """Live runtime observations (no inference)."""

    execution_id: str = ""
    request_id: str = ""
    model_available: bool = True
    backend_available: bool = True
    memory_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    queue_depth: float = Field(default=0.0, ge=0.0)
    latency_p99_ms: float = Field(default=0.0, ge=0.0)
    budget_remaining_usd: float | None = None
    budget_remaining_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    thread_available: int = Field(default=8, ge=0)
    historical_failures: int = Field(default=0, ge=0)
    context_tokens_needed: int = Field(default=0, ge=0)
    tools_required: bool = False
    reasoning_tokens_needed: int = Field(default=0, ge=0)
    latency_slo_ms: float = Field(default=4000.0, ge=0.0)
    max_memory_gb: float = Field(default=16.0, ge=0.0)
    max_cost_usd: float | None = None
    backend_health: dict[str, float] = Field(default_factory=dict)
    model_health: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=utc_now)


class ComponentHealth(_Frozen):
    """Health for one model or backend component."""

    name: str
    kind: str = "model"
    state: HealthState = HealthState.UNKNOWN
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class HealthReport(_Frozen):
    """Aggregate health evaluation result."""

    health_score: float = Field(default=0.0, ge=0.0, le=1.0)
    state: HealthState = HealthState.UNKNOWN
    model_health: list[ComponentHealth] = Field(default_factory=list)
    backend_health: list[ComponentHealth] = Field(default_factory=list)
    factors: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=utc_now)


class FallbackCandidate(_Frozen):
    """One alternative execution configuration."""

    candidate_id: str
    model_id: str
    backend: str = "llama_cpp"
    quant: str = "Q5_K_M"
    context_length: int = 8192
    thread_count: int = 8
    reasoning_budget: int = 512
    tools_enabled: bool = True
    cascade_strategy: CascadeStrategy = CascadeStrategy.SEQUENTIAL
    dimensions_changed: list[FallbackDimension] = Field(default_factory=list)
    quality_delta: float = 0.0
    latency_delta: float = 0.0
    cost_delta: float = 0.0
    memory_delta: float = 0.0
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScoredCandidate(_Frozen):
    """Candidate plus deterministic score factors."""

    candidate: FallbackCandidate
    score: float
    factors: dict[str, float] = Field(default_factory=dict)


class RecoveryRecord(_Frozen):
    """Append-only recovery history entry."""

    record_id: str
    execution_id: str = ""
    fallback_reason: str = ""
    previous_model: str = ""
    new_model: str = ""
    previous_backend: str = ""
    new_backend: str = ""
    previous_quant: str = ""
    new_quant: str = ""
    quality_delta: float = 0.0
    latency_delta: float = 0.0
    budget_delta: float = 0.0
    recovery_success: bool = False
    decision: DecisionKind = DecisionKind.CONTINUE
    experience_ref: str | None = None
    recorded_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION


class ResilienceDecision(_Frozen):
    """Engine output: continue, transition, or degrade-notify."""

    kind: DecisionKind
    policy_id: str | None = None
    health_score: float = 0.0
    alternative: Any = None  # AlternativeExecutionPlan | None (avoid cycle)
    scored: ScoredCandidate | None = None
    reasons: list[str] = Field(default_factory=list)
    decided_at: datetime = Field(default_factory=utc_now)
