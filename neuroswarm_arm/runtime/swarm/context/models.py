"""Shared Pydantic bases, enums, and reference handles for Swarm Context."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ConflictPolicy(str, Enum):
    """How merge resolves overlapping fields."""

    PREFER_PARENT = "prefer_parent"
    PREFER_CHILD = "prefer_child"
    UNION = "union"
    SUM_USAGE = "sum_usage"
    RAISE = "raise"


class SerializationFormat(str, Enum):
    JSON = "json"
    YAML = "yaml"


class ContextRefKind(str, Enum):
    MEM0 = "mem0"
    OKF = "okf"
    KNOWLEDGE = "knowledge"
    TOOL_REGISTRY = "tool_registry"
    AGENT_REGISTRY = "agent_registry"
    TASK_GRAPH = "task_graph"
    CHECKPOINT = "checkpoint"
    EXPERIENCE = "experience"
    ACR_SNAPSHOT = "acr_snapshot"
    GENERIC = "generic"


class ExternalRef(_Base):
    """Opaque handle to an external subsystem resource (no ownership)."""

    kind: ContextRefKind = ContextRefKind.GENERIC
    ref_id: str = ""
    uri: str = ""
    version: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ref_id", "uri", "version")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    def is_empty(self) -> bool:
        return not self.ref_id and not self.uri


class RegistryHandle(_Base):
    """Lightweight registry pointer (tool or agent)."""

    registry_id: str = ""
    revision: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.registry_id


class TaskGraphRef(_Base):
    """Reference to a TaskGraph definition — does not own the graph object."""

    graph_id: str = ""
    content_hash: str = ""
    name: str = ""
    version: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.graph_id and not self.content_hash


class TelemetryContext(_Base):
    """Opaque telemetry baggage for ROF / dashboards."""

    envelope_id: str = ""
    budget_id: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HistoryEntry(_Frozen):
    """Append-only history record."""

    event_type: str
    timestamp: str
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# Re-export for convenience
__all__ = [
    "ConflictPolicy",
    "SerializationFormat",
    "ContextRefKind",
    "ExternalRef",
    "RegistryHandle",
    "TaskGraphRef",
    "TelemetryContext",
    "HistoryEntry",
    "_Base",
    "_Frozen",
]
