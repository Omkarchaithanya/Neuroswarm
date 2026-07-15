"""Execution snapshot and alternative plan types (DIPA-compatible patch, no DIPA import)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ._utils import utc_now
from .models import (
    CascadeStrategy,
    DecisionKind,
    FallbackDimension,
    WorkloadHint,
    _Frozen,
)
from .versioning import SCHEMA_VERSION


class ExecutionSnapshot(_Frozen):
    """RMRE-owned view of the active execution configuration."""

    execution_id: str = ""
    request_id: str = ""
    model: str = "tier2"
    backend: str = "llama_cpp"
    quant: str = "Q5_K_M"
    context_length: int = 8192
    thread_count: int = 8
    reasoning_budget: int = 512
    tools_enabled: bool = True
    cascade_strategy: CascadeStrategy = CascadeStrategy.SEQUENTIAL
    use_cascade: bool = True
    workload: WorkloadHint = WorkloadHint.GENERAL
    fallbacks: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=utc_now)
    schema_version: int = SCHEMA_VERSION


class AlternativeExecutionPlan(_Frozen):
    """Optimal alternative execution plan — never executes inference."""

    plan_id: str
    execution_id: str = ""
    model: str
    backend: str = "llama_cpp"
    quant: str = "Q5_K_M"
    context_length: int = 8192
    thread_count: int = 8
    reasoning_budget: int = 512
    tools_enabled: bool = True
    cascade_strategy: CascadeStrategy = CascadeStrategy.SEQUENTIAL
    previous_model: str = ""
    previous_backend: str = ""
    previous_quant: str = ""
    quality_delta: float = 0.0
    latency_delta: float = 0.0
    cost_delta: float = 0.0
    budget_delta: float = 0.0
    reason: str = ""
    dimensions_changed: list[FallbackDimension] = Field(default_factory=list)
    decision: DecisionKind = DecisionKind.TRANSITION
    score: float = 0.0
    score_factors: dict[str, float] = Field(default_factory=dict)
    fallbacks: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    schema_version: int = SCHEMA_VERSION

    def to_plan_patch(self) -> dict[str, Any]:
        """Dict compatible with DIPA ``ExecutionPlan`` field names."""
        return {
            "model": self.model,
            "backend": self.backend,
            "quant": self.quant,
            "fallbacks": list(self.fallbacks),
            "use_cascade": True,
            "metadata": {
                **dict(self.metadata),
                "rmre_plan_id": self.plan_id,
                "rmre_reason": self.reason,
                "rmre_quality_delta": self.quality_delta,
                "rmre_latency_delta": self.latency_delta,
                "rmre_cost_delta": self.cost_delta,
                "rmre_context_length": self.context_length,
                "rmre_thread_count": self.thread_count,
                "rmre_reasoning_budget": self.reasoning_budget,
                "rmre_tools_enabled": self.tools_enabled,
                "rmre_cascade_strategy": self.cascade_strategy.value,
                "rmre_dimensions_changed": [d.value for d in self.dimensions_changed],
                "rmre_score": self.score,
            },
        }
