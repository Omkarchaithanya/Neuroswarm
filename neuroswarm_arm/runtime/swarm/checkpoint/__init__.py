"""NEXUS-ARM Checkpoint Manager — runtime Fault-Tolerance Kernel.

Immutable recovery points for deterministic workflow resume. Observes execution;
does not drive scheduling. Distinct from Meta Orchestrator checkpoint
*coordination* (``CheckpointCoordinator``) which injects this package via
``ICheckpointManagerPort``.
"""

from __future__ import annotations

from .budget_snapshot import BudgetSnapshot
from .cache import CheckpointCache
from .checkpoint import Checkpoint, CheckpointBuilder
from .context_snapshot import ContextSnapshot
from .events import (
    CheckpointArchived,
    CheckpointCreated,
    CheckpointEvent,
    CheckpointExpired,
    CheckpointRestored,
    EventBus,
    RecoveryPlanned,
    RetentionApplied,
    RollbackPlanned,
    ValidationFailed,
)
from .exceptions import (
    ChecksumMismatchError,
    CheckpointError,
    DuplicateCheckpointError,
    ImmutabilityError,
    LifecycleError,
    NotFoundError,
    PolicyError,
    RecoveryPlanningError,
    RetentionError,
    RollbackPlanningError,
    SerializationError,
    ValidationError,
    VersionMismatchError,
)
from .execution_snapshot import ExecutionSnapshot
from .graph_snapshot import GraphSnapshot
from .interfaces import (
    IAgentRegistryCheckpointPort,
    IArmoraCheckpointPort,
    ICheckpointExperiencePort,
    ICheckpointManagerPort,
    IDashboardCheckpointPort,
    IEventSink,
    IExperienceStorePort,
    IHaoeCheckpointPort,
    IMetricsSink,
    IPerformixCheckpointPort,
    IPolicyEngineCheckpointPort,
    ISwarmContextCheckpointPort,
    ITaskGraphCheckpointPort,
    IWorkflowCoordinationCheckpointPort,
)
from .lifecycle import can_transition, transition
from .manager import CheckpointManager, build_checkpoint_manager
from .metrics import CheckpointMetrics
from .models import (
    ArtifactReference,
    CheckpointEnvelope,
    CheckpointLevel,
    CheckpointStatus,
    FailureContext,
    PolicyKind,
    RecoveryStrategy,
    WorkflowObservation,
)
from .planner import RecoveryPlanner
from .policy import CheckpointPolicy, PolicyEngine
from .recovery import RecoveryPlan
from .repository import ICheckpointRepository, InMemoryRepository, JsonlRepository
from .retention import RetentionManager, RetentionPolicy
from .rollback import RollbackHistory, RollbackMetadataBuilder, RollbackRecord
from .serializer import CheckpointSerializer
from .snapshot import MetricsSnapshot, SnapshotBundle
from .validator import CheckpointValidator
from .versioning import SCHEMA_VERSION, current_version, migrate_payload, register_migration

__version__ = "1.0.0"

__all__ = [
    # Facade
    "CheckpointManager",
    "build_checkpoint_manager",
    "Checkpoint",
    "CheckpointBuilder",
    # Snapshots
    "BudgetSnapshot",
    "ContextSnapshot",
    "ExecutionSnapshot",
    "GraphSnapshot",
    "MetricsSnapshot",
    "SnapshotBundle",
    "ArtifactReference",
    # Recovery / rollback
    "RecoveryPlan",
    "RecoveryPlanner",
    "RecoveryStrategy",
    "RollbackRecord",
    "RollbackHistory",
    "RollbackMetadataBuilder",
    "FailureContext",
    # Policy / retention
    "CheckpointPolicy",
    "PolicyEngine",
    "PolicyKind",
    "RetentionPolicy",
    "RetentionManager",
    "WorkflowObservation",
    # Storage
    "ICheckpointRepository",
    "InMemoryRepository",
    "JsonlRepository",
    "CheckpointCache",
    "CheckpointSerializer",
    "CheckpointValidator",
    "CheckpointEnvelope",
    "CheckpointLevel",
    "CheckpointStatus",
    # Lifecycle / versioning
    "can_transition",
    "transition",
    "SCHEMA_VERSION",
    "current_version",
    "migrate_payload",
    "register_migration",
    # Events / metrics
    "EventBus",
    "CheckpointEvent",
    "CheckpointCreated",
    "CheckpointRestored",
    "CheckpointArchived",
    "CheckpointExpired",
    "RecoveryPlanned",
    "RollbackPlanned",
    "RetentionApplied",
    "ValidationFailed",
    "CheckpointMetrics",
    # Exceptions
    "CheckpointError",
    "ValidationError",
    "DuplicateCheckpointError",
    "NotFoundError",
    "ImmutabilityError",
    "SerializationError",
    "ChecksumMismatchError",
    "VersionMismatchError",
    "LifecycleError",
    "RetentionError",
    "PolicyError",
    "RecoveryPlanningError",
    "RollbackPlanningError",
    # Ports
    "ICheckpointManagerPort",
    "IExperienceStorePort",
    "ICheckpointExperiencePort",
    "IArmoraCheckpointPort",
    "IHaoeCheckpointPort",
    "ITaskGraphCheckpointPort",
    "IAgentRegistryCheckpointPort",
    "ISwarmContextCheckpointPort",
    "IWorkflowCoordinationCheckpointPort",
    "IDashboardCheckpointPort",
    "IPerformixCheckpointPort",
    "IPolicyEngineCheckpointPort",
    "IEventSink",
    "IMetricsSink",
]
