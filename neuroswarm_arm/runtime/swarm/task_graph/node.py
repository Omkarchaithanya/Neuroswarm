"""TaskNode — schedulable unit in the Task Graph DAG."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import NodeStatus, NodeType, Priority
from .models import Budget, ResourceRequirements, RetryPolicy
from .utils import new_id, stable_hash, utc_now


class TaskNode(BaseModel):
    """Immutable-friendly node definition (Pydantic).

    Runtime fields (status, result, error, execution_state, events, metrics)
    live primarily on ExecutionState; mirrors here support serialization snapshots.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str = Field(default_factory=lambda: new_id("n_"))
    name: str = ""
    display_name: str = ""
    description: str = ""
    agent_type: str = ""
    node_type: NodeType = NodeType.TASK
    status: NodeStatus = NodeStatus.PENDING
    priority: Priority = Priority.NORMAL
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    dependencies: list[str] = Field(default_factory=list)
    children: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    timeout: float | None = None
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    condition: dict[str, Any] | None = None
    budget: Budget = Field(default_factory=Budget)

    estimated_cost: float = 0.0
    estimated_latency: float = 0.0
    memory_requirement: int = 0
    required_tools: list[str] = Field(default_factory=list)
    required_models: list[str] = Field(default_factory=list)
    reasoning_budget: float | None = None

    execution_state: dict[str, Any] = Field(default_factory=dict)
    checkpoint_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    error: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)

    subgraph_ref: str | None = None
    handler_key: str | None = None

    @field_validator("timeout")
    @classmethod
    def _timeout_ok(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("timeout must be > 0 when set")
        return v

    @field_validator("priority", mode="before")
    @classmethod
    def _priority_coerce(cls, v: Any) -> Any:
        if isinstance(v, int) and not isinstance(v, Priority):
            return Priority(v)
        return v

    def resources(self) -> ResourceRequirements:
        return ResourceRequirements(
            memory_bytes=self.memory_requirement,
            estimated_cost=self.estimated_cost,
            estimated_latency_ms=self.estimated_latency,
            reasoning_budget=self.reasoning_budget,
        )

    def touch(self) -> TaskNode:
        return self.model_copy(update={"updated_at": utc_now()})

    def clone(self, *, new_id_value: str | None = None) -> TaskNode:
        data = self.model_dump(mode="python")
        data["id"] = new_id_value or new_id("n_")
        data["created_at"] = utc_now()
        data["updated_at"] = utc_now()
        data["status"] = NodeStatus.PENDING
        data["result"] = None
        data["error"] = None
        data["events"] = []
        data["execution_state"] = {}
        return TaskNode.model_validate(data)

    def definition_payload(self) -> dict[str, Any]:
        """Hash-stable payload excluding mutable runtime fields."""
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "agent_type": self.agent_type,
            "node_type": self.node_type.value,
            "priority": int(self.priority),
            "dependencies": list(self.dependencies),
            "children": list(self.children),
            "metadata": self.metadata,
            "tags": list(self.tags),
            "timeout": self.timeout,
            "retry_policy": self.retry_policy.model_dump(mode="json"),
            "condition": self.condition,
            "budget": self.budget.model_dump(mode="json"),
            "estimated_cost": self.estimated_cost,
            "estimated_latency": self.estimated_latency,
            "memory_requirement": self.memory_requirement,
            "required_tools": list(self.required_tools),
            "required_models": list(self.required_models),
            "reasoning_budget": self.reasoning_budget,
            "checkpoint_id": self.checkpoint_id,
            "subgraph_ref": self.subgraph_ref,
            "handler_key": self.handler_key,
        }

    def content_hash(self) -> str:
        return stable_hash(self.definition_payload())

    def __hash__(self) -> int:  # type: ignore[override]
        return int(self.content_hash()[:16], 16)

    def validate_node(self) -> list[str]:
        errs: list[str] = []
        if not self.id:
            errs.append("id is required")
        if self.timeout is not None and self.timeout <= 0:
            errs.append("timeout must be > 0")
        if self.memory_requirement < 0:
            errs.append("memory_requirement must be >= 0")
        if self.estimated_cost < 0:
            errs.append("estimated_cost must be >= 0")
        if self.estimated_latency < 0:
            errs.append("estimated_latency must be >= 0")
        try:
            RetryPolicy.model_validate(self.retry_policy.model_dump())
        except Exception as exc:  # noqa: BLE001
            errs.append(f"invalid retry_policy: {exc}")
        return errs

    def with_runtime(
        self,
        *,
        status: NodeStatus | None = None,
        result: Any = ...,
        error: str | None | object = ...,
        metrics: Mapping[str, Any] | None = None,
        checkpoint_id: str | None | object = ...,
    ) -> TaskNode:
        updates: dict[str, Any] = {"updated_at": utc_now()}
        if status is not None:
            updates["status"] = status
        if result is not ...:
            updates["result"] = result
        if error is not ...:
            updates["error"] = error
        if metrics is not None:
            updates["metrics"] = dict(metrics)
        if checkpoint_id is not ...:
            updates["checkpoint_id"] = checkpoint_id
        return self.model_copy(update=updates)

    def deep_copy_metadata(self) -> dict[str, Any]:
        return deepcopy(self.metadata)
