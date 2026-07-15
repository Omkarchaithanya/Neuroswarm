"""AgentRegistryService — composition root / consumer facade."""

from __future__ import annotations

from typing import Any, Mapping

from .agent import Agent
from .cache import RegistryCache
from .discovery import AgentDiscovery
from .events import EventBus
from .exceptions import AgentNotFoundError
from .heartbeat import HeartbeatRecorder
from .lifecycle import LifecycleState, is_selectable
from .metrics import RegistryMetrics
from .models import SelectionRequest, SelectionResult, ScoringWeights
from .plugins import PluginLoader
from .profile import register_builtin_profiles
from .registry import AgentRegistry
from .selector import AgentSelector
from .serializer import AgentSerializer
from .state import AgentRuntimeState


class AgentRegistryService:
    """Facade implementing consumer Protocols via structural typing."""

    def __init__(
        self,
        registry: AgentRegistry | None = None,
        *,
        events: EventBus | None = None,
        metrics: RegistryMetrics | None = None,
        cache: RegistryCache | None = None,
        weights: ScoringWeights | None = None,
    ) -> None:
        self.events = events or EventBus()
        self.metrics = metrics or RegistryMetrics()
        self.cache = cache or RegistryCache()
        self.registry = registry or AgentRegistry(
            events=self.events,
            metrics=self.metrics,
            on_change=self.cache.invalidate_all,
        )
        # ensure registry shares same bus/metrics if passed in without them
        if registry is not None:
            self.registry.events = self.events
            self.registry.metrics = self.metrics
            self.registry._on_change = self.cache.invalidate_all  # noqa: SLF001

        self.selector = AgentSelector(
            weights=weights,
            cache=self.cache,
            events=self.events,
            metrics=self.metrics,
        )
        self.heartbeat = HeartbeatRecorder(self.registry, events=self.events)
        self.discovery = AgentDiscovery(self.registry.as_list)
        self.plugins = PluginLoader()
        self.serializer = AgentSerializer()
        self._runtime: dict[str, AgentRuntimeState] = {}

    # ---- registration helpers ----
    def register(self, agent: Agent, **kwargs: Any) -> Agent:
        record = self.registry.register(agent, **kwargs)
        self._runtime[record.id] = AgentRuntimeState(
            agent_id=record.id,
            lifecycle=record.status,
        )
        return record

    def unregister(self, agent_id: str) -> Agent:
        self._runtime.pop(agent_id, None)
        return self.registry.unregister(agent_id)

    def select(self, request: SelectionRequest) -> SelectionResult:
        return self.selector.select(self.registry.as_list(), request)

    def select_best(self, request: SelectionRequest, *, require: bool = False):
        return self.selector.select_best(
            self.registry.as_list(), request, require=require
        )

    def runtime_state(self, agent_id: str) -> AgentRuntimeState:
        if agent_id not in self._runtime:
            agent = self.registry.get(agent_id)
            self._runtime[agent_id] = AgentRuntimeState(
                agent_id=agent_id, lifecycle=agent.status
            )
        return self._runtime[agent_id]

    # ---- ITaskGraphAgentResolver ----
    def resolve_agent_type(self, agent_type: str) -> Agent | None:
        matches = [
            a
            for a in self.registry.as_list()
            if a.agent_type == agent_type or a.category == agent_type
        ]
        if not matches:
            # try name
            try:
                return self.registry.get_by_name(agent_type)
            except AgentNotFoundError:
                return None
        # prefer highest priority ready
        matches.sort(key=lambda a: (-a.priority, a.name))
        return matches[0]

    def resolve_agent_id(self, agent_id: str) -> Agent | None:
        return self.registry.get_optional(agent_id)

    # ---- IHAOEAgentCatalog ----
    def list_ready_agents(self) -> list[Agent]:
        return [a for a in self.registry.as_list() if is_selectable(a.status)]

    def has_capability(self, agent_id: str, capability_key: str) -> bool:
        agent = self.registry.get(agent_id)
        return capability_key in agent.capabilities.capability_keys()

    # ---- IArmoraAgentBudgetSource ----
    def estimated_cost(self, agent_id: str) -> float:
        return float(self.registry.get(agent_id).estimated_cost)

    def estimated_tokens(self, agent_id: str) -> float:
        return float(self.registry.get(agent_id).estimated_tokens)

    def budget_hints(self, agent_id: str) -> Mapping[str, Any]:
        agent = self.registry.get(agent_id)
        return {
            "cost_usd": agent.estimated_cost,
            "tokens": agent.estimated_tokens,
            "latency_ms": agent.estimated_latency,
            "memory_bytes": agent.estimated_memory,
            "priority": agent.priority,
        }

    # ---- IDIPAAgentModelHints ----
    def preferred_models(self, agent_id: str) -> list[str]:
        agent = self.registry.get(agent_id)
        return list(agent.capabilities.preferred_models or agent.effective_models())

    def preferred_backend(self, agent_id: str) -> str | None:
        return self.registry.get(agent_id).capabilities.preferred_backend

    def preferred_quantization(self, agent_id: str) -> str | None:
        return self.registry.get(agent_id).capabilities.preferred_quantization

    # ---- IGovernorAgentPriority ----
    def agent_priority(self, agent_id: str) -> int:
        return int(self.registry.get(agent_id).priority)

    def token_preference(self, agent_id: str) -> float | None:
        agent = self.registry.get(agent_id)
        return float(agent.estimated_tokens) if agent.estimated_tokens else None

    # ---- IMemoryAgentNamespace ----
    def memory_namespace(self, agent_id: str) -> str:
        agent = self.registry.get(agent_id)
        return f"agents/{agent.namespace}/{agent.id}"

    def supported_memory(self, agent_id: str) -> list[str]:
        agent = self.registry.get(agent_id)
        return list(agent.supported_memory or agent.capabilities.supported_memory)

    # ---- ISwarmAgentBinding ----
    def bind_node(self, node_id: str, agent_type: str) -> str | None:
        agent = self.resolve_agent_type(agent_type)
        if agent is None:
            return None
        state = self.runtime_state(agent.id)
        self._runtime[agent.id] = state.model_copy(
            update={"bindings": {**state.bindings, node_id: agent.id}}
        ).touch()
        return agent.id

    def select_for_task(self, request: SelectionRequest) -> SelectionResult:
        return self.select(request)

    # ---- IDashboardAgentView ----
    def list_agents(self) -> list[Agent]:
        return self.registry.as_list()

    def agent_health(self, agent_id: str) -> Mapping[str, Any]:
        return self.registry.get(agent_id).health.model_dump(mode="json")

    def metrics_snapshot(self) -> Mapping[str, Any]:
        return self.metrics.snapshot()

    def load_plugins(self) -> int:
        agents = self.plugins.load_all()
        return self.registry.bulk_register(agents, replace_existing=True)


def build_agent_registry(
    *,
    include_builtins: bool = True,
    events: EventBus | None = None,
    metrics: RegistryMetrics | None = None,
    cache: RegistryCache | None = None,
    weights: ScoringWeights | None = None,
    allow_unknown_backend: bool = False,
    allow_unknown_quant: bool = False,
) -> AgentRegistryService:
    """Factory: construct a fully wired AgentRegistryService."""
    bus = events or EventBus()
    mets = metrics or RegistryMetrics()
    cch = cache or RegistryCache()
    registry = AgentRegistry(
        events=bus,
        metrics=mets,
        on_change=cch.invalidate_all,
        allow_unknown_backend=allow_unknown_backend,
        allow_unknown_quant=allow_unknown_quant,
    )
    service = AgentRegistryService(
        registry,
        events=bus,
        metrics=mets,
        cache=cch,
        weights=weights,
    )
    if include_builtins:
        register_builtin_profiles(service.registry, replace_existing=True)
        for agent in service.registry.as_list():
            service._runtime[agent.id] = AgentRuntimeState(  # noqa: SLF001
                agent_id=agent.id,
                lifecycle=agent.status,
            )
    return service
