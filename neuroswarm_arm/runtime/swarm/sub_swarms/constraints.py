"""Hard constraints for swarm templates."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SwarmConstraints(_Base):
    """Limits and required resources enforced at validation/selection time."""

    min_agents: int = 1
    max_agents: int | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    required_models: list[str] = Field(default_factory=list)
    required_backends: list[str] = Field(default_factory=list)
    required_memory: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    required_budget_keys: list[str] = Field(default_factory=list)
    max_cost_usd: float | None = None
    max_memory_bytes: int | None = None
    max_latency_ms: float | None = None
    max_cpu_cores: float | None = None
    max_tokens: float | None = None
    execution_policies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("min_agents")
    @classmethod
    def _min_agents(cls, v: int) -> int:
        if v < 1:
            raise ValueError("min_agents must be >= 1")
        return v

    def agent_count_ok(self, count: int) -> bool:
        if count < self.min_agents:
            return False
        if self.max_agents is not None and count > self.max_agents:
            return False
        return True

    def within_budget(
        self,
        *,
        cost: float | None = None,
        latency_ms: float | None = None,
        memory_bytes: int | None = None,
        cpu_cores: float | None = None,
        tokens: float | None = None,
    ) -> bool:
        if self.max_cost_usd is not None and cost is not None and cost > self.max_cost_usd:
            return False
        if (
            self.max_latency_ms is not None
            and latency_ms is not None
            and latency_ms > self.max_latency_ms
        ):
            return False
        if (
            self.max_memory_bytes is not None
            and memory_bytes is not None
            and memory_bytes > self.max_memory_bytes
        ):
            return False
        if (
            self.max_cpu_cores is not None
            and cpu_cores is not None
            and cpu_cores > self.max_cpu_cores
        ):
            return False
        if self.max_tokens is not None and tokens is not None and tokens > self.max_tokens:
            return False
        return True
