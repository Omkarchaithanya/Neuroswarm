"""NEXUS-ARM Rollback Manager — runtime Transaction & Recovery subsystem.

Deterministic workflow consistency restoration after partial execution failures.
Distinct from Checkpoint Manager (snapshots + where-to-resume) and Meta
Orchestrator ``RollbackCoordinator`` (notify only).

Does not execute workflows. Does not schedule. Does not run inference.
"""

from __future__ import annotations

from .consistency import ConsistencyChecker
from .events import (
    EventBus,
    RecoveryFinished,
    RecoveryPrepared,
    RollbackCancelled,
    RollbackCompleted,
    RollbackEvent,
    RollbackFailed,
    RollbackStarted,
    RollbackValidated,
)
from .exceptions import (
    CancellationError,
    ChecksumMismatchError,
    ConsistencyError,
    DuplicateRollbackError,
    ImmutabilityError,
    LifecycleError,
    NotFoundError,
    PolicyError,
    RollbackError,
    RollbackExecutionError,
    RollbackPlanningError,
    SerializationError,
    ValidationError,
    VersionMismatchError,
)
from .execution import RollbackExecutor, RollbackResult, stamp_metadata
from .history import HistoryEntry, RollbackHistoryStore, RollbackHistoryView
from .interfaces import (
    IAgentRegistryRollbackPort,
    IArmoraBudgetRollbackPort,
    ICheckpointRollbackPort,
    IDashboardRollbackPort,
    IEventSink,
    IExperienceStoreRollbackPort,
    IHaoeRollbackPort,
    IMetricsSink,
    IPerformixRollbackPort,
    IPolicyPredicatePort,
    IRecoveryPlannerPort,
    IRollbackManagerPort,
    ISwarmContextRollbackPort,
    ITaskGraphRollbackPort,
    IWorkflowCoordinationRollbackPort,
)
from .lifecycle import can_transition, transition
from .manager import RollbackManager, build_rollback_manager
from .metadata import RollbackExecutionMetadata
from .metrics import RollbackMetrics
from .models import (
    ArtifactReference,
    ConsistencyReport,
    ConsistencyViolation,
    ConsistencyViolationKind,
    FailureObservation,
    InitiatorKind,
    PolicyKind,
    RollbackAnalytics,
    RollbackLevel,
    RollbackObservation,
    RollbackStatus,
    RollbackStrategyKind,
)
from .planner import RollbackPlanner
from .policies import (
    PolicyEngine,
    RollbackPolicy,
    always_rollback,
    automatic_rollback,
    budget_rollback,
    custom_rollback,
    failure_rollback,
    latency_rollback,
    manual_rollback,
    threshold_rollback,
)
from .recovery import RecoveryExecutionMetadata, RollbackPlan
from .repository import IRollbackRepository, InMemoryRepository, JsonlRepository
from .rollback import RollbackBuilder, RollbackOperation
from .serializer import RollbackSerializer, dumps, loads
from .snapshots import (
    BudgetSnapshotRef,
    ContextSnapshotRef,
    ExecutionSnapshotRef,
    GraphSnapshotRef,
    MetadataSnapshotRef,
    RollbackSnapshotBundle,
)
from .strategy import (
    CustomStrategy,
    IRollbackStrategy,
    RestartNodeStrategy,
    RestartSubgraphStrategy,
    RestartWorkflowStrategy,
    ResumeCheckpointStrategy,
    RollbackBudgetStrategy,
    RollbackContextStrategy,
    RollbackMetadataStrategy,
    strategy_for,
)
from .validator import RollbackValidator
from .versioning import SCHEMA_VERSION, current_version, migrate_payload, register_migration

__version__ = "1.0.0"

__all__ = [
    # Facade
    "RollbackManager",
    "build_rollback_manager",
    "RollbackOperation",
    "RollbackBuilder",
    # Planning / recovery
    "RollbackPlan",
    "RollbackPlanner",
    "RecoveryExecutionMetadata",
    "RollbackExecutor",
    "RollbackResult",
    "stamp_metadata",
    # Strategies
    "IRollbackStrategy",
    "ResumeCheckpointStrategy",
    "RestartWorkflowStrategy",
    "RestartNodeStrategy",
    "RestartSubgraphStrategy",
    "RollbackContextStrategy",
    "RollbackBudgetStrategy",
    "RollbackMetadataStrategy",
    "CustomStrategy",
    "strategy_for",
    # Policies
    "RollbackPolicy",
    "PolicyEngine",
    "PolicyKind",
    "always_rollback",
    "manual_rollback",
    "automatic_rollback",
    "threshold_rollback",
    "budget_rollback",
    "latency_rollback",
    "failure_rollback",
    "custom_rollback",
    # Consistency / validation
    "ConsistencyChecker",
    "ConsistencyReport",
    "ConsistencyViolation",
    "ConsistencyViolationKind",
    "RollbackValidator",
    "can_transition",
    "transition",
    # Snapshots / metadata
    "GraphSnapshotRef",
    "ExecutionSnapshotRef",
    "ContextSnapshotRef",
    "BudgetSnapshotRef",
    "MetadataSnapshotRef",
    "RollbackSnapshotBundle",
    "RollbackExecutionMetadata",
    "ArtifactReference",
    # History / analytics
    "HistoryEntry",
    "RollbackHistoryStore",
    "RollbackHistoryView",
    "RollbackAnalytics",
    # Models / enums
    "RollbackLevel",
    "RollbackStrategyKind",
    "RollbackStatus",
    "InitiatorKind",
    "FailureObservation",
    "RollbackObservation",
    # Storage / serde
    "IRollbackRepository",
    "InMemoryRepository",
    "JsonlRepository",
    "RollbackSerializer",
    "dumps",
    "loads",
    "SCHEMA_VERSION",
    "current_version",
    "migrate_payload",
    "register_migration",
    # Events / metrics
    "EventBus",
    "RollbackEvent",
    "RollbackStarted",
    "RollbackCompleted",
    "RollbackFailed",
    "RollbackCancelled",
    "RollbackValidated",
    "RecoveryPrepared",
    "RecoveryFinished",
    "RollbackMetrics",
    # Ports
    "IRollbackManagerPort",
    "ICheckpointRollbackPort",
    "IRecoveryPlannerPort",
    "ITaskGraphRollbackPort",
    "ISwarmContextRollbackPort",
    "IArmoraBudgetRollbackPort",
    "IWorkflowCoordinationRollbackPort",
    "IAgentRegistryRollbackPort",
    "IExperienceStoreRollbackPort",
    "IHaoeRollbackPort",
    "IDashboardRollbackPort",
    "IPerformixRollbackPort",
    "IPolicyPredicatePort",
    "IEventSink",
    "IMetricsSink",
    # Exceptions
    "RollbackError",
    "ValidationError",
    "DuplicateRollbackError",
    "NotFoundError",
    "ImmutabilityError",
    "SerializationError",
    "ChecksumMismatchError",
    "VersionMismatchError",
    "LifecycleError",
    "ConsistencyError",
    "PolicyError",
    "RollbackPlanningError",
    "RollbackExecutionError",
    "CancellationError",
]
