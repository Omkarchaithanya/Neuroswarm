"""ExecutionContext — task-graph execution surface (no executor logic)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from ._utils import utc_now
from .models import _Base


class TimelineEvent(_Base):
    node_id: str = ""
    status: str = ""
    timestamp: datetime = Field(default_factory=utc_now)
    detail: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeFailure(_Base):
    node_id: str
    error: str = ""
    attempt: int = 0
    timestamp: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionContext(_Base):
    """Mutable execution view shared across agents.

    Holds graph refs and node bookkeeping — not the TaskGraph object itself.
    """

    run_id: str = ""
    numa_node: int | None = None
    pool_hint: str = ""
    timeout_s: float | None = None
    baggage: dict[str, Any] = Field(default_factory=dict)
    available_tools: list[str] = Field(default_factory=list)
    available_models: list[str] = Field(default_factory=list)
    confidence: float | None = None

    current_node: str | None = None
    current_agent: str | None = None
    completed_nodes: list[str] = Field(default_factory=list)
    pending_nodes: list[str] = Field(default_factory=list)
    failed_nodes: list[str] = Field(default_factory=list)
    retries: dict[str, int] = Field(default_factory=dict)
    failures: list[NodeFailure] = Field(default_factory=list)
    checkpoint_ids: list[str] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    node_results: dict[str, Any] = Field(default_factory=dict)
    node_statuses: dict[str, str] = Field(default_factory=dict)
    depth: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence")
    @classmethod
    def _conf(cls, v: float | None) -> float | None:
        if v is not None and (v < 0.0 or v > 1.0):
            raise ValueError("confidence must be in [0, 1]")
        return v

    @field_validator("depth")
    @classmethod
    def _depth(cls, v: int) -> int:
        if v < 0:
            raise ValueError("depth must be >= 0")
        return v

    @field_validator("timeout_s")
    @classmethod
    def _timeout(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("timeout_s must be >= 0")
        return v

    def mark_completed(self, node_id: str, *, result: Any = None, status: str = "SUCCEEDED") -> ExecutionContext:
        completed = list(self.completed_nodes)
        if node_id not in completed:
            completed.append(node_id)
        pending = [n for n in self.pending_nodes if n != node_id]
        results = dict(self.node_results)
        if result is not None:
            results[node_id] = result
        statuses = dict(self.node_statuses)
        statuses[node_id] = status
        timeline = list(self.timeline) + [
            TimelineEvent(node_id=node_id, status=status, detail="completed")
        ]
        return self.model_copy(
            update={
                "completed_nodes": completed,
                "pending_nodes": pending,
                "node_results": results,
                "node_statuses": statuses,
                "timeline": timeline,
                "current_node": node_id,
            }
        )

    def mark_failed(self, node_id: str, error: str, *, attempt: int = 0) -> ExecutionContext:
        failed = list(self.failed_nodes)
        if node_id not in failed:
            failed.append(node_id)
        failures = list(self.failures) + [
            NodeFailure(node_id=node_id, error=error, attempt=attempt)
        ]
        retries = dict(self.retries)
        retries[node_id] = retries.get(node_id, 0) + 1
        statuses = dict(self.node_statuses)
        statuses[node_id] = "FAILED"
        timeline = list(self.timeline) + [
            TimelineEvent(node_id=node_id, status="FAILED", detail=error)
        ]
        return self.model_copy(
            update={
                "failed_nodes": failed,
                "failures": failures,
                "retries": retries,
                "node_statuses": statuses,
                "timeline": timeline,
                "current_node": node_id,
            }
        )

    def child(self) -> ExecutionContext:
        from ._utils import new_id

        return self.model_copy(
            update={
                "run_id": new_id("run_"),
                "baggage": dict(self.baggage),
                "available_tools": list(self.available_tools),
                "available_models": list(self.available_models),
                "depth": self.depth + 1,
                "timeline": [],
            },
            deep=True,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")
