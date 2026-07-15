"""Workflow-level history rollups linking immutable execution records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator, model_validator

from ._utils import new_id, stable_hash, utc_now
from .models import _Frozen


class WorkflowRecord(_Frozen):
    """Immutable workflow history envelope spanning one or more executions."""

    workflow_id: str = Field(default_factory=lambda: new_id("wf_"))
    request_id: str | None = None
    session_id: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    execution_ids: list[str] = Field(default_factory=list)
    task_graph_reference: str | None = None
    execution_plan_reference: str | None = None
    success: bool = True
    failure_reason: str | None = None
    total_latency: float = 0.0
    total_cost: float = 0.0
    average_quality: float | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    content_hash: str | None = None

    @field_validator("total_latency", "total_cost")
    @classmethod
    def _non_neg(cls, v: float) -> float:
        if v < 0:
            raise ValueError("must be >= 0")
        return v

    @field_validator("average_quality")
    @classmethod
    def _quality_ok(cls, v: float | None) -> float | None:
        if v is None:
            return v
        if v < 0.0 or v > 1.0:
            raise ValueError("average_quality must be in [0, 1]")
        return v

    @field_validator("version")
    @classmethod
    def _version_pos(cls, v: int) -> int:
        if v < 1:
            raise ValueError("version must be >= 1")
        return v

    @model_validator(mode="after")
    def _ensure_hash(self) -> WorkflowRecord:
        if self.content_hash:
            return self
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        object.__setattr__(self, "content_hash", stable_hash(payload))
        return self
