"""Typed errors for the Agent Registry subsystem."""

from __future__ import annotations


class AgentRegistryError(Exception):
    """Base error for the Agent Registry subsystem."""


class ValidationError(AgentRegistryError):
    """Agent or capability failed validation."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class AgentNotFoundError(AgentRegistryError):
    """Requested agent id/name is not present."""

    def __init__(self, key: str) -> None:
        super().__init__(f"agent not found: {key}")
        self.key = key


class DuplicateAgentError(ValidationError):
    """Duplicate id or name in the registry."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message, field=field)


class LifecycleError(AgentRegistryError):
    """Illegal lifecycle state transition."""

    def __init__(self, agent_id: str, current: object, target: object) -> None:
        super().__init__(f"invalid lifecycle for {agent_id}: {current} -> {target}")
        self.agent_id = agent_id
        self.current = current
        self.target = target


class FrozenAgentError(AgentRegistryError):
    """Mutation attempted on a frozen agent definition."""

    def __init__(self, agent_id: str) -> None:
        super().__init__(f"agent is frozen: {agent_id}")
        self.agent_id = agent_id


class SerializationError(AgentRegistryError):
    """Serialize / deserialize failure."""


class SelectionError(AgentRegistryError):
    """No eligible agent for selection request."""


class PluginError(AgentRegistryError):
    """Plugin load or registration failure."""


class CacheError(AgentRegistryError):
    """Registry cache operation failure."""
