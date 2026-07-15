"""Pydantic models for Task Graph policies, budgets, and reports."""

from __future__ import annotations

import random
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import BackoffStrategy


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RetryPolicy(_FrozenModel):
    """Per-node retry policy with backoff + jitter."""

    max_attempts: int = 3
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    backoff_base_s: float = 0.05
    backoff_factor: float = 2.0
    backoff_max_s: float = 5.0
    jitter: bool = True
    jitter_ratio: float = 0.1
    retry_on_timeout: bool = False
    retry_on_failure: bool = True
    retry_conditions: tuple[str, ...] = ()

    @field_validator("max_attempts")
    @classmethod
    def _attempts_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_attempts must be >= 1")
        return v

    @field_validator("backoff_base_s", "backoff_factor", "backoff_max_s", "jitter_ratio")
    @classmethod
    def _non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("backoff/jitter values must be >= 0")
        return v

    def delay_for(self, attempt: int) -> float:
        """Return delay in seconds for 0-based attempt index."""
        if self.backoff_strategy is BackoffStrategy.CONSTANT:
            delay = self.backoff_base_s
        elif self.backoff_strategy is BackoffStrategy.LINEAR:
            delay = self.backoff_base_s * (attempt + 1)
        else:
            delay = self.backoff_base_s * (self.backoff_factor**attempt)
        delay = min(delay, self.backoff_max_s)
        if self.jitter and delay > 0:
            span = delay * self.jitter_ratio
            delay = max(0.0, delay + random.uniform(-span, span))
        return delay


class Budget(_FrozenModel):
    """Resource / cost budget attached to a node or graph."""

    tokens: float | None = None
    cost_usd: float | None = None
    energy_j: float | None = None
    latency_ms: float | None = None
    memory_bytes: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def remaining_ok(self, *, used_cost: float = 0.0, used_latency_ms: float = 0.0) -> bool:
        if self.cost_usd is not None and used_cost > self.cost_usd:
            return False
        if self.latency_ms is not None and used_latency_ms > self.latency_ms:
            return False
        return True


class ResourceRequirements(_FrozenModel):
    """Estimated resource needs for scheduling / critical-path analysis."""

    memory_bytes: int = 0
    estimated_cost: float = 0.0
    estimated_latency_ms: float = 0.0
    cpu_weight: float = 1.0
    reasoning_budget: float | None = None

    @field_validator("memory_bytes")
    @classmethod
    def _mem_non_neg(cls, v: int) -> int:
        if v < 0:
            raise ValueError("memory_bytes must be >= 0")
        return v


class TimeoutPolicy(_FrozenModel):
    """Timeout scopes: node / subgraph / workflow."""

    node_timeout_s: float | None = None
    subgraph_timeout_s: float | None = None
    workflow_timeout_s: float | None = None

    @field_validator("node_timeout_s", "subgraph_timeout_s", "workflow_timeout_s")
    @classmethod
    def _positive_or_none(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("timeouts must be > 0 when set")
        return v


class ValidationIssue(_FrozenModel):
    """Single human-readable validation finding."""

    code: str
    message: str
    severity: str = "error"  # error | warning
    node_id: str | None = None
    edge: tuple[str, str] | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(_FrozenModel):
    """Aggregate validation result."""

    issues: tuple[ValidationIssue, ...] = ()
    graph_id: str | None = None

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def format(self) -> str:
        if not self.issues:
            return "Validation OK"
        lines = [f"Validation {'OK with warnings' if self.ok else 'FAILED'}"]
        if self.graph_id:
            lines[0] += f" (graph={self.graph_id})"
        for issue in self.issues:
            loc = ""
            if issue.node_id:
                loc = f" node={issue.node_id}"
            elif issue.edge:
                loc = f" edge={issue.edge[0]}->{issue.edge[1]}"
            lines.append(f"  [{issue.severity.upper()}] {issue.code}:{loc} {issue.message}")
        return "\n".join(lines)


class NodeMetricsSnapshot(_FrozenModel):
    """Serializable metrics snapshot for a node."""

    execution_time_s: float = 0.0
    queue_time_s: float = 0.0
    retries: int = 0
    failures: int = 0
    estimated_latency_ms: float = 0.0
    estimated_cost: float = 0.0
    memory_estimate_bytes: int = 0


class GraphMetricsSnapshot(_FrozenModel):
    """Serializable metrics snapshot for a whole graph run."""

    execution_time_s: float = 0.0
    queue_time_s: float = 0.0
    retries: int = 0
    failures: int = 0
    parallelism: float = 0.0
    depth: int = 0
    width: int = 0
    critical_path_length: int = 0
    critical_path_latency_ms: float = 0.0
    estimated_latency_ms: float = 0.0
    estimated_cost: float = 0.0
    memory_estimate_bytes: int = 0
    nodes_succeeded: int = 0
    nodes_failed: int = 0
    nodes_skipped: int = 0
    nodes_cancelled: int = 0


class GraphMeta(_FrozenModel):
    """Graph-level metadata and versioning."""

    version: str = "1.0.0"
    schema_version: int = 1
    name: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str = ""
    parent_graph_id: str | None = None
