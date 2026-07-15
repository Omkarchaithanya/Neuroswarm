"""Execution profile for swarm templates."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import SwarmRetryPolicy


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ExecutionProfile(_Base):
    """How a swarm template expects to be coordinated (not scheduled here)."""

    parallelism: int = 1
    priority: int = 50
    timeout_s: float | None = 300.0
    retry_policy: SwarmRetryPolicy = Field(default_factory=SwarmRetryPolicy)
    fail_fast: bool = False
    checkpoint_enabled: bool = True
    max_concurrent_agents: int = 8
    execution_policy: str = "sequential"  # sequential | parallel | hybrid
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("parallelism", "max_concurrent_agents")
    @classmethod
    def _positive_int(cls, v: int) -> int:
        if v < 1:
            raise ValueError("must be >= 1")
        return v

    @field_validator("priority")
    @classmethod
    def _priority_range(cls, v: int) -> int:
        if v < 0 or v > 100:
            raise ValueError("priority must be 0..100")
        return v

    @field_validator("timeout_s")
    @classmethod
    def _timeout_ok(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("timeout_s must be >= 0")
        return v
