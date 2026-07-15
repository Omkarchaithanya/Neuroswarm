"""Agent — strongly typed runtime capability record."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._utils import new_id, stable_hash, utc_now
from .capability import AgentCapability
from .health import HealthRecord
from .lifecycle import LifecycleState
from .metadata import normalize_labels, normalize_tags
from .models import ExecutionLimits, ResourceRequirements


class Agent(BaseModel):
    """Canonical agent capability record for the NEXUS-ARM registry."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str = Field(default_factory=lambda: new_id("agt_"))
    name: str
    display_name: str = ""
    description: str = ""
    version: str = "1.0.0"
    namespace: str = "nexus.agents"
    agent_type: str = "generic"
    category: str = "general"
    status: LifecycleState = LifecycleState.CREATED
    priority: int = 50
    owner: str = ""
    tags: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    configuration: dict[str, Any] = Field(default_factory=dict)
    runtime_requirements: dict[str, Any] = Field(default_factory=dict)
    resource_requirements: ResourceRequirements = Field(default_factory=ResourceRequirements)
    execution_limits: ExecutionLimits = Field(default_factory=ExecutionLimits)

    capabilities: AgentCapability = Field(default_factory=AgentCapability)

    # Denormalized for indexing (synced from capabilities when empty)
    supported_tasks: list[str] = Field(default_factory=list)
    supported_tools: list[str] = Field(default_factory=list)
    supported_models: list[str] = Field(default_factory=list)
    supported_backends: list[str] = Field(default_factory=list)
    supported_quantizations: list[str] = Field(default_factory=list)
    supported_memory: list[str] = Field(default_factory=list)
    supported_context: list[str] = Field(default_factory=list)

    estimated_latency: float = 0.0
    estimated_cost: float = 0.0
    estimated_tokens: float = 0.0
    estimated_memory: int = 0
    estimated_cpu: float = 0.0
    estimated_threads: int = 0
    confidence_score: float = 0.8

    health: HealthRecord = Field(default_factory=HealthRecord)
    metrics: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)

    checkpoint_support: bool = False
    streaming_support: bool = False
    parallel_support: bool = False
    retry_support: bool = True
    timeout_support: bool = True
    future_distributed_support: bool = False

    frozen: bool = False

    @field_validator("name")
    @classmethod
    def _name_required(cls, v: str) -> str:
        if not str(v).strip():
            raise ValueError("name is required")
        return str(v).strip()

    @field_validator("priority")
    @classmethod
    def _priority_range(cls, v: int) -> int:
        if v < 0 or v > 100:
            raise ValueError("priority must be in [0, 100]")
        return v

    @field_validator("confidence_score")
    @classmethod
    def _confidence(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("confidence_score must be in [0, 1]")
        return v

    @field_validator(
        "estimated_latency",
        "estimated_cost",
        "estimated_tokens",
        "estimated_cpu",
    )
    @classmethod
    def _non_neg_f(cls, v: float) -> float:
        if v < 0:
            raise ValueError("must be >= 0")
        return v

    @field_validator("estimated_memory", "estimated_threads")
    @classmethod
    def _non_neg_i(cls, v: int) -> int:
        if v < 0:
            raise ValueError("must be >= 0")
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, v: Any) -> list[str]:
        if v is None:
            return []
        return normalize_tags(list(v))

    @field_validator("labels", mode="before")
    @classmethod
    def _labels(cls, v: Any) -> dict[str, str]:
        if v is None:
            return {}
        return normalize_labels(dict(v))

    @model_validator(mode="after")
    def _sync_denorm_and_display(self) -> Agent:
        """Sync denormalized fields in-place (must return self for __init__)."""
        caps = self.capabilities

        def _set(field: str, value: Any) -> None:
            object.__setattr__(self, field, value)

        if not self.display_name:
            _set("display_name", self.name)
        if not self.supported_tasks and caps.supported_tasks:
            _set("supported_tasks", list(caps.supported_tasks))
        if not self.supported_tools and caps.supported_tools:
            _set("supported_tools", list(caps.supported_tools))
        if not self.supported_models and caps.supported_models:
            _set("supported_models", list(caps.supported_models))
        if not self.supported_backends and caps.supported_backends:
            _set("supported_backends", list(caps.supported_backends))
        if not self.supported_quantizations and caps.supported_quantizations:
            _set("supported_quantizations", list(caps.supported_quantizations))
        if not self.supported_memory and caps.supported_memory:
            _set("supported_memory", list(caps.supported_memory))

        if caps.supports_streaming and not self.streaming_support:
            _set("streaming_support", True)
        if caps.supports_checkpoint and not self.checkpoint_support:
            _set("checkpoint_support", True)
        if caps.supports_parallel and not self.parallel_support:
            _set("parallel_support", True)
        if caps.supports_retry and not self.retry_support:
            _set("retry_support", True)

        return self

    def touch(self) -> Agent:
        return self.model_copy(update={"updated_at": utc_now()})

    def content_hash(self) -> str:
        payload = self.model_dump(
            mode="json",
            exclude={"health", "metrics", "events", "created_at", "updated_at"},
        )
        return stable_hash(payload)

    def clone(self, *, new_id_value: str | None = None, new_name: str | None = None) -> Agent:
        data = self.model_dump(mode="python")
        data["id"] = new_id_value or new_id("agt_")
        if new_name:
            data["name"] = new_name
        data["created_at"] = utc_now()
        data["updated_at"] = utc_now()
        data["status"] = LifecycleState.CREATED
        data["frozen"] = False
        data["events"] = []
        data["health"] = HealthRecord().model_dump(mode="python")
        return Agent.model_validate(data)

    def freeze(self) -> Agent:
        return self.model_copy(update={"frozen": True, "updated_at": utc_now()})

    def with_status(self, status: LifecycleState) -> Agent:
        return self.model_copy(update={"status": status, "updated_at": utc_now()})

    def bump_version(self, version: str) -> Agent:
        return self.model_copy(update={"version": version, "updated_at": utc_now()})

    def effective_tools(self) -> list[str]:
        return list(self.supported_tools or self.capabilities.supported_tools)

    def effective_models(self) -> list[str]:
        return list(self.supported_models or self.capabilities.supported_models)

    def effective_backends(self) -> list[str]:
        return list(self.supported_backends or self.capabilities.supported_backends)

    def effective_quants(self) -> list[str]:
        return list(
            self.supported_quantizations or self.capabilities.supported_quantizations
        )

    def effective_tasks(self) -> list[str]:
        return list(self.supported_tasks or self.capabilities.supported_tasks)
