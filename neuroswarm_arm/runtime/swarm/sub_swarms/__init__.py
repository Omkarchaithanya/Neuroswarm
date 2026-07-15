"""NEXUS-ARM Sub Swarms — reusable multi-agent workflow templates.

Public API for ``neuroswarm_arm.runtime.swarm.sub_swarms``.

Sub Swarms describe workflows. They never schedule, plan, or run inference.
"""

from __future__ import annotations

from .builder import SwarmBuilder
from .builtins import (
    BUILTIN_TEMPLATE_FACTORIES,
    all_builtin_templates,
    analysis_swarm,
    benchmark_swarm,
    coding_swarm,
    documentation_swarm,
    planning_swarm,
    register_builtin_templates,
    research_swarm,
    tool_execution_swarm,
)
from .capabilities import SwarmCapability
from .composer import SwarmComposer
from .constraints import SwarmConstraints
from .events import (
    EventBus,
    SelectionPerformed,
    SwarmArchived,
    SwarmDeprecated,
    SwarmDisabled,
    SwarmEvent,
    SwarmRegistered,
    SwarmSelected,
    SwarmUpdated,
    SwarmValidated,
)
from .exceptions import (
    CircularCompositionError,
    CompositionError,
    DuplicateTemplateError,
    LifecycleError,
    SelectionError,
    SerializationError,
    SubSwarmError,
    TemplateNotFoundError,
    ValidationError,
    VersionError,
)
from .execution_profile import ExecutionProfile
from .interfaces import (
    IAgentRegistryLookupPort,
    IArmoraBudgetHintsPort,
    ICheckpointTemplatePort,
    IDashboardSwarmView,
    IDipaModelHintsPort,
    IExperienceStoreTemplatePort,
    IHaoeWorkflowHintsPort,
    IMetaOrchestratorTemplatePort,
    ISubSwarmCatalog,
    ISwarmContextDefaultsPort,
    ITaskGraphTemplatePort,
)
from .lifecycle import LifecycleState, can_transition, is_selectable, transition
from .manager import SubSwarmManager, build_sub_swarm_manager
from .metadata import SwarmMetadata, merge_labels, merge_tags, normalize_labels, normalize_tags
from .metrics import SwarmMetrics
from .models import (
    BudgetConstraints,
    ExecutableWorkflowDescription,
    ScoreBreakdown,
    ScoredTemplate,
    ScoringWeights,
    SwarmRetryPolicy,
    SwarmSelectionRequest,
    SwarmSelectionResult,
    TaskGraphReference,
    ValidationIssue,
    ValidationReport,
)
from .profile import (
    BackendProfile,
    BudgetProfile,
    ContextProfile,
    CostProfile,
    LatencyProfile,
    MemoryProfile,
    ModelProfile,
    ResourceProfile,
    SwarmProfile,
)
from .registry import SubSwarmRegistry
from .selector import SwarmSelector, score_template
from .serializer import SwarmSerializer, dumps, loads
from .template import SwarmTemplate
from .validator import SwarmValidator
from .versioning import (
    SCHEMA_VERSION,
    bump_semver,
    compare_semver,
    migrate,
    parse_semver,
    versions_compatible,
)

__version__ = "1.0.0"

__all__ = [
    # core
    "SwarmTemplate",
    "SwarmBuilder",
    "SwarmComposer",
    "SubSwarmRegistry",
    "SubSwarmManager",
    "build_sub_swarm_manager",
    "SwarmValidator",
    "SwarmSelector",
    "score_template",
    "SwarmSerializer",
    "dumps",
    "loads",
    "SCHEMA_VERSION",
    # profiles / constraints
    "SwarmProfile",
    "ResourceProfile",
    "BudgetProfile",
    "LatencyProfile",
    "CostProfile",
    "MemoryProfile",
    "ModelProfile",
    "BackendProfile",
    "ContextProfile",
    "ExecutionProfile",
    "SwarmCapability",
    "SwarmConstraints",
    "SwarmMetadata",
    "SwarmRetryPolicy",
    "TaskGraphReference",
    # selection / validation
    "SwarmSelectionRequest",
    "SwarmSelectionResult",
    "ScoredTemplate",
    "ScoreBreakdown",
    "ScoringWeights",
    "BudgetConstraints",
    "ValidationReport",
    "ValidationIssue",
    "ExecutableWorkflowDescription",
    # lifecycle
    "LifecycleState",
    "can_transition",
    "transition",
    "is_selectable",
    # events / metrics
    "EventBus",
    "SwarmEvent",
    "SwarmRegistered",
    "SwarmUpdated",
    "SwarmSelected",
    "SwarmValidated",
    "SwarmDeprecated",
    "SwarmArchived",
    "SwarmDisabled",
    "SelectionPerformed",
    "SwarmMetrics",
    # builtins
    "BUILTIN_TEMPLATE_FACTORIES",
    "all_builtin_templates",
    "register_builtin_templates",
    "research_swarm",
    "coding_swarm",
    "documentation_swarm",
    "tool_execution_swarm",
    "analysis_swarm",
    "planning_swarm",
    "benchmark_swarm",
    # versioning / metadata helpers
    "parse_semver",
    "compare_semver",
    "bump_semver",
    "migrate",
    "versions_compatible",
    "normalize_tags",
    "normalize_labels",
    "merge_tags",
    "merge_labels",
    # exceptions
    "SubSwarmError",
    "ValidationError",
    "TemplateNotFoundError",
    "DuplicateTemplateError",
    "LifecycleError",
    "CompositionError",
    "CircularCompositionError",
    "SerializationError",
    "SelectionError",
    "VersionError",
    # interfaces
    "ITaskGraphTemplatePort",
    "IAgentRegistryLookupPort",
    "ISwarmContextDefaultsPort",
    "IMetaOrchestratorTemplatePort",
    "IArmoraBudgetHintsPort",
    "IHaoeWorkflowHintsPort",
    "IDipaModelHintsPort",
    "IExperienceStoreTemplatePort",
    "ICheckpointTemplatePort",
    "IDashboardSwarmView",
    "ISubSwarmCatalog",
]
