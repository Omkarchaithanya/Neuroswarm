"""NEXUS-ARM Experience Store — immutable historical execution database.

Public API for ``neuroswarm_arm.runtime.swarm.experience``.

Distinct from ``neuroswarm_arm.evolution.rl.experience_store.ExperienceStore``
(AROP offline RL). This package records completed workflow executions for
benchmarking, policy evolution, analytics, and future GEPA / offline RL.
"""

from __future__ import annotations

from .analytics import AnalyticsReport, ExperienceAnalytics
from .artifacts import ArtifactRef
from .dataset import DatasetGenerator, ExperienceDataset
from .events import (
    AnalyticsUpdated,
    DatasetGenerated,
    EventBus,
    ExecutionArchived,
    ExecutionExported,
    ExecutionRecorded,
    ExperienceEvent,
    WorkflowRecorded,
)
from .exceptions import (
    DuplicateIdError,
    ExperienceStoreError,
    ExportError,
    ImmutabilityError,
    ImportError,
    LifecycleError,
    NotFoundError,
    RetentionError,
    SerializationError,
    ValidationError,
    VersionMismatchError,
)
from .execution_plan import ExecutionPlan, PlanStep
from .execution_record import ExecutionRecord
from .exporter import ExperienceExporter
from .filters import (
    ExperienceFilter,
    by_agent,
    by_backend,
    by_date_range,
    by_model,
    by_success,
    by_workflow,
    with_predicate,
)
from .importer import ExperienceImporter
from .indexing import ExperienceIndex
from .interfaces import (
    IAgentRegistryExperiencePort,
    IArmoraExperiencePort,
    IBenchmarkRuntimePort,
    ICheckpointExperiencePort,
    IDashboardExperiencePort,
    IExperienceStorePort,
    IHaoeExperiencePort,
    IPerformixExperiencePort,
    IPolicyEnginePort,
    ISwarmContextExperiencePort,
    ITaskGraphExperiencePort,
    IWorkflowCoordinationPort,
)
from .lifecycle import can_transition, transition
from .metrics import ExperienceMetrics
from .models import (
    AgentAssignment,
    ArtifactKind,
    BudgetSnapshot,
    CheckpointRef,
    DatasetKind,
    ExportFormat,
    RecordEnvelope,
    RecordLifecycle,
    ResourceUsage,
    TokenUsage,
    ToolCallRef,
)
from .quality import QualityScore
from .query import QueryEngine
from .recorder import ExperienceRecorder
from .repository import InMemoryRepository, JsonlRepository
from .retention import RetentionManager, RetentionPolicy
from .serializer import SCHEMA_VERSION, ExperienceSerializer, dumps, loads, migrate
from .store import ExperienceStore, build_experience_store
from .validators import (
    validate_execution_record,
    validate_metrics,
    validate_quality,
    validate_workflow_record,
)
from .workflow_record import WorkflowRecord

__version__ = "1.0.0"

__all__ = [
    "__version__",
    # facade
    "ExperienceStore",
    "build_experience_store",
    # records
    "ExecutionRecord",
    "ExecutionPlan",
    "PlanStep",
    "WorkflowRecord",
    "QualityScore",
    "ArtifactRef",
    "ArtifactKind",
    "TokenUsage",
    "BudgetSnapshot",
    "AgentAssignment",
    "ToolCallRef",
    "CheckpointRef",
    "ResourceUsage",
    "RecordEnvelope",
    "RecordLifecycle",
    "DatasetKind",
    "ExportFormat",
    # core services
    "ExperienceRecorder",
    "QueryEngine",
    "ExperienceFilter",
    "ExperienceAnalytics",
    "AnalyticsReport",
    "RetentionManager",
    "RetentionPolicy",
    "ExperienceExporter",
    "ExperienceImporter",
    "DatasetGenerator",
    "ExperienceDataset",
    "ExperienceSerializer",
    "ExperienceIndex",
    "ExperienceMetrics",
    "InMemoryRepository",
    "JsonlRepository",
    "EventBus",
    "ExperienceEvent",
    # events
    "ExecutionRecorded",
    "ExecutionArchived",
    "ExecutionExported",
    "DatasetGenerated",
    "AnalyticsUpdated",
    "WorkflowRecorded",
    # filters helpers
    "by_workflow",
    "by_agent",
    "by_model",
    "by_backend",
    "by_success",
    "by_date_range",
    "with_predicate",
    # lifecycle / serde
    "can_transition",
    "transition",
    "SCHEMA_VERSION",
    "dumps",
    "loads",
    "migrate",
    "validate_execution_record",
    "validate_workflow_record",
    "validate_quality",
    "validate_metrics",
    # ports
    "IExperienceStorePort",
    "IArmoraExperiencePort",
    "IHaoeExperiencePort",
    "ITaskGraphExperiencePort",
    "IAgentRegistryExperiencePort",
    "ISwarmContextExperiencePort",
    "IWorkflowCoordinationPort",
    "ICheckpointExperiencePort",
    "IDashboardExperiencePort",
    "IPerformixExperiencePort",
    "IBenchmarkRuntimePort",
    "IPolicyEnginePort",
    # errors
    "ExperienceStoreError",
    "ValidationError",
    "DuplicateIdError",
    "NotFoundError",
    "ImmutabilityError",
    "SerializationError",
    "ExportError",
    "ImportError",
    "RetentionError",
    "VersionMismatchError",
    "LifecycleError",
]
