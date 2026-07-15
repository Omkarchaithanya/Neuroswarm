"""NEXUS-ARM Agent Registry — runtime capability catalog.

Public API for ``neuroswarm_arm.runtime.swarm.agent_registry``.
"""

from __future__ import annotations

from .agent import Agent
from .cache import RegistryCache
from .capability import AgentCapability
from .discovery import AgentDiscovery
from .events import EventBus, RegistryEvent
from .exceptions import (
    AgentNotFoundError,
    AgentRegistryError,
    DuplicateAgentError,
    FrozenAgentError,
    LifecycleError,
    PluginError,
    SelectionError,
    SerializationError,
    ValidationError,
)
from .health import HealthRecord
from .heartbeat import HeartbeatRecorder
from .interfaces import (
    IArmoraAgentBudgetSource,
    IDashboardAgentView,
    IDIPAAgentModelHints,
    IGovernorAgentPriority,
    IHAOEAgentCatalog,
    IMemoryAgentNamespace,
    ISwarmAgentBinding,
    ITaskGraphAgentResolver,
)
from .lifecycle import LifecycleState, can_transition, is_selectable, transition
from .loader import AgentLoader
from .metrics import RegistryMetrics
from .models import (
    BudgetConstraints,
    ExecutionLimits,
    ResourceRequirements,
    ScoreBreakdown,
    ScoredAgent,
    ScoringWeights,
    SelectionRequest,
    SelectionResult,
)
from .plugins import CallablePlugin, IAgentPlugin, PluginLoader
from .profile import (
    BUILTIN_PROFILE_FACTORIES,
    all_builtin_profiles,
    coding_agent,
    coordinator_agent,
    evaluator_agent,
    memory_agent,
    planning_agent,
    register_builtin_profiles,
    research_agent,
    reviewer_agent,
    router_agent,
    summarizer_agent,
    tool_agent,
)
from .registry import AgentRegistry
from .registry_service import AgentRegistryService, build_agent_registry
from .selector import AgentSelector
from .serializer import SCHEMA_VERSION, AgentSerializer, dumps, loads
from .state import AgentRuntimeState

__all__ = [
    # core
    "Agent",
    "AgentCapability",
    "AgentRegistry",
    "AgentRegistryService",
    "build_agent_registry",
    "register_builtin_profiles",
    "all_builtin_profiles",
    "BUILTIN_PROFILE_FACTORIES",
    # selection
    "AgentSelector",
    "SelectionRequest",
    "SelectionResult",
    "ScoredAgent",
    "ScoreBreakdown",
    "ScoringWeights",
    "BudgetConstraints",
    # lifecycle / health / state
    "LifecycleState",
    "can_transition",
    "transition",
    "is_selectable",
    "HealthRecord",
    "HeartbeatRecorder",
    "AgentRuntimeState",
    # infra
    "EventBus",
    "RegistryEvent",
    "RegistryMetrics",
    "RegistryCache",
    "AgentDiscovery",
    "AgentLoader",
    "AgentSerializer",
    "dumps",
    "loads",
    "SCHEMA_VERSION",
    "PluginLoader",
    "IAgentPlugin",
    "CallablePlugin",
    # models
    "ResourceRequirements",
    "ExecutionLimits",
    # interfaces
    "ITaskGraphAgentResolver",
    "IHAOEAgentCatalog",
    "IArmoraAgentBudgetSource",
    "IDIPAAgentModelHints",
    "IGovernorAgentPriority",
    "IMemoryAgentNamespace",
    "ISwarmAgentBinding",
    "IDashboardAgentView",
    # profiles
    "research_agent",
    "coding_agent",
    "planning_agent",
    "reviewer_agent",
    "memory_agent",
    "tool_agent",
    "router_agent",
    "evaluator_agent",
    "summarizer_agent",
    "coordinator_agent",
    # errors
    "AgentRegistryError",
    "ValidationError",
    "AgentNotFoundError",
    "DuplicateAgentError",
    "LifecycleError",
    "FrozenAgentError",
    "SerializationError",
    "SelectionError",
    "PluginError",
]

__version__ = "1.0.0"
