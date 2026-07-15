"""ToolContext — available / selected tools (refs only, no execution)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .models import RegistryHandle, _Base


class ToolCapability(_Base):
    name: str
    description: str = ""
    permissions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolHistoryEntry(_Base):
    tool_name: str
    node_id: str = ""
    status: str = ""
    latency_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolContext(_Base):
    """Tool surface visible to agents — registry handle + selection state."""

    registry: RegistryHandle = Field(default_factory=RegistryHandle)
    available_tools: list[str] = Field(default_factory=list)
    selected_tools: list[str] = Field(default_factory=list)
    capabilities: list[ToolCapability] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    history: list[ToolHistoryEntry] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")
