"""Shared Pydantic models for Sub Swarm requests, descriptions, and scoring."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class TaskGraphReference(_Base):
    """Reference to a Task Graph template (never an executor handle)."""

    graph_id: str = ""
    graph_name: str = ""
    schema_version: int = 1
    snapshot: dict[str, Any] | None = None

    @property
    def is_present(self) -> bool:
        return bool(self.graph_id or self.graph_name or self.snapshot)


class SwarmRetryPolicy(_Base):
    """Local retry policy mirror (avoids tight coupling to task_graph)."""

    max_attempts: int = 3
    backoff_base_s: float = 0.05
    backoff_factor: float = 2.0
    backoff_max_s: float = 5.0
    jitter: bool = True
    retry_on_timeout: bool = False
    retry_on_failure: bool = True

    @field_validator("max_attempts")
    @classmethod
    def _attempts_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_attempts must be >= 1")
        return v

    @field_validator("backoff_base_s", "backoff_factor", "backoff_max_s")
    @classmethod
    def _non_neg(cls, v: float) -> float:
        if v < 0:
            raise ValueError("must be >= 0")
        return v


class BudgetConstraints(_Base):
    """Selection-time budget envelope."""

    max_cost_usd: float | None = None
    max_latency_ms: float | None = None
    max_tokens: float | None = None
    max_memory_bytes: int | None = None
    max_cpu_cores: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScoringWeights(_Base):
    """Normalized weights for deterministic swarm selection."""

    capability: float = 0.30
    budget_fit: float = 0.20
    latency: float = 0.15
    cost: float = 0.15
    agent_coverage: float = 0.15
    priority: float = 0.05

    def normalized(self) -> ScoringWeights:
        vals = [
            self.capability,
            self.budget_fit,
            self.latency,
            self.cost,
            self.agent_coverage,
            self.priority,
        ]
        total = sum(vals) or 1.0
        return ScoringWeights(
            capability=self.capability / total,
            budget_fit=self.budget_fit / total,
            latency=self.latency / total,
            cost=self.cost / total,
            agent_coverage=self.agent_coverage / total,
            priority=self.priority / total,
        )


class SwarmSelectionRequest(_Base):
    """Inputs for deterministic swarm template selection."""

    workflow_type: str = ""
    task_type: str = ""
    required_capabilities: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    required_models: list[str] = Field(default_factory=list)
    required_backends: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    preferred_templates: list[str] = Field(default_factory=list)
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    budget: BudgetConstraints = Field(default_factory=BudgetConstraints)
    context_keys: list[str] = Field(default_factory=list)
    limit: int = 10
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("limit")
    @classmethod
    def _limit_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("limit must be >= 1")
        return v


class ScoreBreakdown(_Base):
    capability: float = 0.0
    budget_fit: float = 0.0
    latency: float = 0.0
    cost: float = 0.0
    agent_coverage: float = 0.0
    priority: float = 0.0


class ScoredTemplate(_Base):
    template_id: str
    name: str
    score: float
    breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    reasons: list[str] = Field(default_factory=list)


class SwarmSelectionResult(_Base):
    request_hash: str = ""
    templates: list[ScoredTemplate] = Field(default_factory=list)
    rejected: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutableWorkflowDescription(_Base):
    """Composer output for Meta Orchestrator / HAOE — description only, no run."""

    template_id: str
    template_name: str = ""
    template_version: str = "1.0.0"
    workflow_type: str = ""
    task_graph: TaskGraphReference = Field(default_factory=TaskGraphReference)
    agents: list[str] = Field(default_factory=list)
    optional_agents: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    required_models: list[str] = Field(default_factory=list)
    required_backends: list[str] = Field(default_factory=list)
    context_defaults: dict[str, Any] = Field(default_factory=dict)
    budget_defaults: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    execution_profile: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(_Base):
    code: str
    message: str
    field: str | None = None
    severity: str = "error"  # error | warning


class ValidationReport(_Base):
    ok: bool = True
    issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def add(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        severity: str = "error",
    ) -> None:
        self.issues.append(
            ValidationIssue(
                code=code, message=message, field=field, severity=severity
            )
        )
        if severity == "error":
            self.ok = False
