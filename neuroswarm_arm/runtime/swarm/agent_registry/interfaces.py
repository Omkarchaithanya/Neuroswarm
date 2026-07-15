"""Consumer-facing Protocol interfaces (no kernel imports)."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from .agent import Agent
from .models import SelectionRequest, SelectionResult


@runtime_checkable
class ITaskGraphAgentResolver(Protocol):
    """Task Graph Planner: resolve agent_type / id to Agent definition."""

    def resolve_agent_type(self, agent_type: str) -> Agent | None: ...

    def resolve_agent_id(self, agent_id: str) -> Agent | None: ...


@runtime_checkable
class IHAOEAgentCatalog(Protocol):
    """HAOE: list ready agents and capability checks."""

    def list_ready_agents(self) -> list[Agent]: ...

    def has_capability(self, agent_id: str, capability_key: str) -> bool: ...


@runtime_checkable
class IArmoraAgentBudgetSource(Protocol):
    """ARMORA: seed budget envelopes from registry estimates."""

    def estimated_cost(self, agent_id: str) -> float: ...

    def estimated_tokens(self, agent_id: str) -> float: ...

    def budget_hints(self, agent_id: str) -> Mapping[str, Any]: ...


@runtime_checkable
class IDIPAAgentModelHints(Protocol):
    """DIPA: preferred models / backends / quantizations."""

    def preferred_models(self, agent_id: str) -> list[str]: ...

    def preferred_backend(self, agent_id: str) -> str | None: ...

    def preferred_quantization(self, agent_id: str) -> str | None: ...


@runtime_checkable
class IGovernorAgentPriority(Protocol):
    """RTG / Governor: priority and token preference."""

    def agent_priority(self, agent_id: str) -> int: ...

    def token_preference(self, agent_id: str) -> float | None: ...


@runtime_checkable
class IMemoryAgentNamespace(Protocol):
    """Memory Runtime: namespace + supported memory kinds."""

    def memory_namespace(self, agent_id: str) -> str: ...

    def supported_memory(self, agent_id: str) -> list[str]: ...


@runtime_checkable
class ISwarmAgentBinding(Protocol):
    """Swarm Runtime: bind task node to agent id."""

    def bind_node(self, node_id: str, agent_type: str) -> str | None: ...

    def select_for_task(self, request: SelectionRequest) -> SelectionResult: ...


@runtime_checkable
class IDashboardAgentView(Protocol):
    """Dashboard: list agents + health + metrics."""

    def list_agents(self) -> list[Agent]: ...

    def agent_health(self, agent_id: str) -> Mapping[str, Any]: ...

    def metrics_snapshot(self) -> Mapping[str, Any]: ...


@runtime_checkable
class IEventSink(Protocol):
    def emit(self, event: Any) -> None: ...


@runtime_checkable
class IMetricsSink(Protocol):
    def record(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, str] | None = None,
    ) -> None: ...
