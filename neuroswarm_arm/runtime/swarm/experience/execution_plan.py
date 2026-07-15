"""Execution plan references recorded with completed workflows."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from ._utils import new_id, stable_hash
from .models import _Frozen


class PlanStep(_Frozen):
    """Single planned step (agent / model / backend binding)."""

    step_id: str
    node_id: str | None = None
    agent_id: str | None = None
    agent_type: str | None = None
    model: str | None = None
    backend: str | None = None
    quantization: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlan(_Frozen):
    """Immutable planned execution graph snapshot (definition only)."""

    plan_id: str = Field(default_factory=lambda: new_id("plan_"))
    workflow_id: str | None = None
    steps: list[PlanStep] = Field(default_factory=list)
    agent_bindings: dict[str, str] = Field(default_factory=dict)
    model_bindings: dict[str, str] = Field(default_factory=dict)
    backend_bindings: dict[str, str] = Field(default_factory=dict)
    content_hash: str | None = None
    version: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("version")
    @classmethod
    def _version_pos(cls, v: int) -> int:
        if v < 1:
            raise ValueError("version must be >= 1")
        return v

    @model_validator(mode="after")
    def _ensure_hash(self) -> ExecutionPlan:
        if self.content_hash:
            return self
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        object.__setattr__(self, "content_hash", stable_hash(payload))
        return self
