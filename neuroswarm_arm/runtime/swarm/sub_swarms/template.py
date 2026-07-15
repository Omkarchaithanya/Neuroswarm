"""SwarmTemplate — reusable multi-agent workflow description."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ._utils import stable_hash, utc_now
from .capabilities import SwarmCapability
from .constraints import SwarmConstraints
from .execution_profile import ExecutionProfile
from .lifecycle import LifecycleState
from .metadata import SwarmMetadata, normalize_labels, normalize_tags
from .models import SwarmRetryPolicy, TaskGraphReference
from .profile import SwarmProfile
from .versioning import bump_semver


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SwarmTemplate(_Base):
    """Reusable workflow template composed of Task Graph + agent refs + profiles.

    Does **not** schedule, plan, or run inference.
    """

    id: str
    name: str
    display_name: str = ""
    description: str = ""
    version: str = "1.0.0"
    category: str = "general"
    workflow_type: str = ""
    task_graph_reference: TaskGraphReference = Field(default_factory=TaskGraphReference)
    required_agents: list[str] = Field(default_factory=list)
    optional_agents: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    required_models: list[str] = Field(default_factory=list)
    required_backends: list[str] = Field(default_factory=list)
    required_memory: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    required_budget: list[str] = Field(default_factory=list)
    execution_profile: ExecutionProfile = Field(default_factory=ExecutionProfile)
    profile: SwarmProfile = Field(default_factory=SwarmProfile)
    capabilities: SwarmCapability = Field(default_factory=SwarmCapability)
    constraints: SwarmConstraints = Field(default_factory=SwarmConstraints)
    estimated_cost: float = 0.0
    estimated_latency: float = 0.0
    estimated_memory: int = 0
    estimated_cpu: float = 0.0
    estimated_tokens: float = 0.0
    parallelism: int = 1
    priority: int = 50
    timeout: float | None = 300.0
    retry_policy: SwarmRetryPolicy = Field(default_factory=SwarmRetryPolicy)
    metadata: SwarmMetadata = Field(default_factory=SwarmMetadata)
    tags: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    status: LifecycleState = LifecycleState.CREATED
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    frozen: bool = False

    @field_validator("id", "name")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not str(v).strip():
            raise ValueError("must be non-empty")
        return str(v).strip()

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, v: object) -> list[str]:
        if v is None:
            return []
        return normalize_tags(list(v) if not isinstance(v, str) else [v])  # type: ignore[arg-type]

    @field_validator("labels", mode="before")
    @classmethod
    def _labels(cls, v: object) -> dict[str, str]:
        if v is None:
            return {}
        return normalize_labels(dict(v))  # type: ignore[arg-type]

    @field_validator(
        "estimated_cost",
        "estimated_latency",
        "estimated_cpu",
        "estimated_tokens",
    )
    @classmethod
    def _non_neg_float(cls, v: float) -> float:
        if v < 0:
            raise ValueError("must be >= 0")
        return v

    @field_validator("estimated_memory", "parallelism")
    @classmethod
    def _non_neg_int(cls, v: int) -> int:
        if v < 0:
            raise ValueError("must be >= 0")
        return v

    @field_validator("parallelism")
    @classmethod
    def _parallelism_min(cls, v: int) -> int:
        if v < 1:
            raise ValueError("parallelism must be >= 1")
        return v

    @model_validator(mode="after")
    def _defaults(self) -> SwarmTemplate:
        if not self.display_name:
            object.__setattr__(self, "display_name", self.name.replace("_", " ").title())
        # Keep top-level parallelism/priority/timeout in sync with execution_profile
        # when profile still has defaults and template set explicit values.
        return self

    def touch(self) -> SwarmTemplate:
        return self.model_copy(update={"updated_at": utc_now()})

    def evolve(self, **fields: Any) -> SwarmTemplate:
        if self.frozen and fields:
            raise ValueError(f"template is frozen: {self.id}")
        payload = {**fields, "updated_at": utc_now()}
        return self.model_copy(update=payload)

    def clone(
        self,
        *,
        new_id: str | None = None,
        new_name: str | None = None,
        reset_lifecycle: bool = True,
    ) -> SwarmTemplate:
        data = self.model_dump(mode="python")
        data["id"] = new_id or f"{self.id}.clone"
        data["name"] = new_name or f"{self.name}_clone"
        data["frozen"] = False
        data["created_at"] = utc_now()
        data["updated_at"] = utc_now()
        if reset_lifecycle:
            data["status"] = LifecycleState.CREATED
        meta = dict(data.get("metadata") or {})
        provenance = list(meta.get("provenance") or [])
        provenance.append(self.id)
        meta["provenance"] = provenance
        data["metadata"] = meta
        return SwarmTemplate.model_validate(data)

    def content_hash(self) -> str:
        payload = self.model_dump(
            mode="json",
            exclude={"created_at", "updated_at", "status", "frozen"},
        )
        return stable_hash(payload)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def bump_version(self, *, part: str = "patch") -> SwarmTemplate:
        return self.evolve(version=bump_semver(self.version, part=part))

    def freeze(self) -> SwarmTemplate:
        return self.evolve(frozen=True)

    def all_agents(self) -> list[str]:
        return list(dict.fromkeys([*self.required_agents, *self.optional_agents]))

    def agent_count(self) -> int:
        return len(self.all_agents())
