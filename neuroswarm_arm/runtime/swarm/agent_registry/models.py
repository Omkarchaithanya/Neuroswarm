"""Shared Pydantic models for Agent Registry requests and constraints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ResourceRequirements(_Base):
    """Estimated / required compute resources."""

    memory_bytes: int = 0
    cpu_cores: float = 0.0
    threads: int = 0
    gpu_count: int = 0
    estimated_cost: float = 0.0
    estimated_latency_ms: float = 0.0
    estimated_tokens: float = 0.0
    reasoning_budget: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("memory_bytes", "threads", "gpu_count")
    @classmethod
    def _non_neg_int(cls, v: int) -> int:
        if v < 0:
            raise ValueError("must be >= 0")
        return v

    @field_validator("cpu_cores", "estimated_cost", "estimated_latency_ms", "estimated_tokens")
    @classmethod
    def _non_neg_float(cls, v: float) -> float:
        if v < 0:
            raise ValueError("must be >= 0")
        return v


class ExecutionLimits(_Base):
    """Hard caps on agent execution (enforced by consumers, not this registry)."""

    max_concurrent: int = 1
    max_retries: int = 3
    timeout_s: float | None = None
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    max_latency_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("max_concurrent", "max_retries")
    @classmethod
    def _positive_int(cls, v: int) -> int:
        if v < 1:
            raise ValueError("must be >= 1")
        return v


class BudgetConstraints(_Base):
    """Selection-time budget envelope."""

    max_cost_usd: float | None = None
    max_latency_ms: float | None = None
    max_tokens: float | None = None
    max_memory_bytes: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SelectionRequest(_Base):
    """Inputs for deterministic agent selection."""

    task: str = ""
    task_tags: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    required_models: list[str] = Field(default_factory=list)
    required_backends: list[str] = Field(default_factory=list)
    required_quantizations: list[str] = Field(default_factory=list)
    preferred_agents: list[str] = Field(default_factory=list)
    budget: BudgetConstraints = Field(default_factory=BudgetConstraints)
    execution_plan: dict[str, Any] = Field(default_factory=dict)
    min_health: float = 0.0
    min_confidence: float = 0.0
    limit: int = 5
    include_busy: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("limit")
    @classmethod
    def _limit_ok(cls, v: int) -> int:
        if v < 1:
            raise ValueError("limit must be >= 1")
        return v

    @field_validator("min_health", "min_confidence")
    @classmethod
    def _unit_interval(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("must be in [0, 1]")
        return v


class ScoreBreakdown(_Base):
    """Per-signal score components (0..1 each before weighting)."""

    capability: float = 0.0
    tools: float = 0.0
    models: float = 0.0
    backend_quant: float = 0.0
    latency: float = 0.0
    cost: float = 0.0
    health: float = 0.0
    priority: float = 0.0
    confidence: float = 0.0
    resources: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return self.model_dump(mode="python")


class ScoredAgent(_Base):
    agent_id: str
    name: str
    score: float
    breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    reasons: list[str] = Field(default_factory=list)


class SelectionResult(_Base):
    """Ranked selection output."""

    request_hash: str = ""
    agents: list[ScoredAgent] = Field(default_factory=list)
    rejected: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def best(self) -> ScoredAgent | None:
        return self.agents[0] if self.agents else None


class ScoringWeights(_Base):
    """Configurable weights for deterministic scoring (must sum ~1.0)."""

    capability: float = 0.25
    tools: float = 0.15
    models: float = 0.10
    backend_quant: float = 0.10
    latency: float = 0.10
    cost: float = 0.10
    health: float = 0.10
    priority: float = 0.05
    confidence: float = 0.05
    resources: float = 0.0

    def normalized(self) -> ScoringWeights:
        data = self.model_dump(mode="python")
        total = sum(float(v) for v in data.values())
        if total <= 0:
            return self
        return ScoringWeights(**{k: float(v) / total for k, v in data.items()})
