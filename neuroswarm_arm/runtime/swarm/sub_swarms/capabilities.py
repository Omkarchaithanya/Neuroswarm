"""Capability requirements declared by a swarm template."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SwarmCapability(_Base):
    """Capability set a template requires from agents / runtime."""

    required_capabilities: list[str] = Field(default_factory=list)
    optional_capabilities: list[str] = Field(default_factory=list)
    supported_tasks: list[str] = Field(default_factory=list)
    supported_workflows: list[str] = Field(default_factory=list)
    supports_parallel: bool = True
    supports_checkpoint: bool = True
    supports_streaming: bool = False
    min_agents: int = 1
    max_agents: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("min_agents")
    @classmethod
    def _min_agents(cls, v: int) -> int:
        if v < 1:
            raise ValueError("min_agents must be >= 1")
        return v

    def capability_keys(self) -> list[str]:
        return list(
            dict.fromkeys(
                [*self.required_capabilities, *self.optional_capabilities]
            )
        )

    def covers(self, required: list[str]) -> bool:
        have = set(self.required_capabilities) | set(self.optional_capabilities)
        return set(required).issubset(have)
