"""Swarm profiles — resource, budget, latency, cost, memory, model, backend, context."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .execution_profile import ExecutionProfile


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ResourceProfile(_Base):
    memory_bytes: int = 0
    cpu_cores: float = 0.0
    threads: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("memory_bytes", "threads")
    @classmethod
    def _non_neg_int(cls, v: int) -> int:
        if v < 0:
            raise ValueError("must be >= 0")
        return v

    @field_validator("cpu_cores")
    @classmethod
    def _non_neg_float(cls, v: float) -> float:
        if v < 0:
            raise ValueError("must be >= 0")
        return v


class BudgetProfile(_Base):
    max_cost_usd: float | None = None
    max_tokens: float | None = None
    envelope_template: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class LatencyProfile(_Base):
    target_ms: float | None = None
    p95_ms: float | None = None
    timeout_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CostProfile(_Base):
    estimated_usd: float = 0.0
    max_usd: float | None = None
    currency: str = "USD"
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryProfile(_Base):
    kinds: list[str] = Field(default_factory=list)
    namespace: str = ""
    max_bytes: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelProfile(_Base):
    preferred_models: list[str] = Field(default_factory=list)
    allowed_models: list[str] = Field(default_factory=list)
    preferred_quantization: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class BackendProfile(_Base):
    preferred_backend: str = ""
    allowed_backends: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextProfile(_Base):
    required_keys: list[str] = Field(default_factory=list)
    optional_keys: list[str] = Field(default_factory=list)
    defaults: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SwarmProfile(_Base):
    """Aggregate profile used for composition overrides and selection hints."""

    resource: ResourceProfile = Field(default_factory=ResourceProfile)
    budget: BudgetProfile = Field(default_factory=BudgetProfile)
    execution: ExecutionProfile = Field(default_factory=ExecutionProfile)
    latency: LatencyProfile = Field(default_factory=LatencyProfile)
    cost: CostProfile = Field(default_factory=CostProfile)
    memory: MemoryProfile = Field(default_factory=MemoryProfile)
    model: ModelProfile = Field(default_factory=ModelProfile)
    backend: BackendProfile = Field(default_factory=BackendProfile)
    context: ContextProfile = Field(default_factory=ContextProfile)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def merge(self, other: SwarmProfile) -> SwarmProfile:
        """Right-biased shallow merge of nested profiles."""
        return SwarmProfile(
            resource=ResourceProfile(
                **{
                    **self.resource.model_dump(),
                    **{
                        k: v
                        for k, v in other.resource.model_dump().items()
                        if v not in (0, 0.0, None, "", [], {})
                    },
                }
            ),
            budget=BudgetProfile(
                **{**self.budget.model_dump(), **other.budget.model_dump()}
            ),
            execution=other.execution
            if other.execution != ExecutionProfile()
            else self.execution,
            latency=LatencyProfile(
                **{**self.latency.model_dump(), **other.latency.model_dump()}
            ),
            cost=CostProfile(**{**self.cost.model_dump(), **other.cost.model_dump()}),
            memory=MemoryProfile(
                kinds=list(dict.fromkeys([*self.memory.kinds, *other.memory.kinds])),
                namespace=other.memory.namespace or self.memory.namespace,
                max_bytes=other.memory.max_bytes
                if other.memory.max_bytes is not None
                else self.memory.max_bytes,
                metadata={**self.memory.metadata, **other.memory.metadata},
            ),
            model=ModelProfile(
                preferred_models=other.model.preferred_models
                or self.model.preferred_models,
                allowed_models=list(
                    dict.fromkeys(
                        [*self.model.allowed_models, *other.model.allowed_models]
                    )
                ),
                preferred_quantization=other.model.preferred_quantization
                or self.model.preferred_quantization,
                metadata={**self.model.metadata, **other.model.metadata},
            ),
            backend=BackendProfile(
                preferred_backend=other.backend.preferred_backend
                or self.backend.preferred_backend,
                allowed_backends=list(
                    dict.fromkeys(
                        [
                            *self.backend.allowed_backends,
                            *other.backend.allowed_backends,
                        ]
                    )
                ),
                metadata={**self.backend.metadata, **other.backend.metadata},
            ),
            context=ContextProfile(
                required_keys=list(
                    dict.fromkeys(
                        [*self.context.required_keys, *other.context.required_keys]
                    )
                ),
                optional_keys=list(
                    dict.fromkeys(
                        [*self.context.optional_keys, *other.context.optional_keys]
                    )
                ),
                defaults={**self.context.defaults, **other.context.defaults},
                metadata={**self.context.metadata, **other.context.metadata},
            ),
            metadata={**self.metadata, **other.metadata},
        )
