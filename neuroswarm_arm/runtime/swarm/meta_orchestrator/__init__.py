"""Meta Orchestrator — NEXUS-ARM workflow coordination engine.

Coordinates Task Graph readiness, Agent Registry candidate selection,
Swarm Context propagation, and HAOE execution requests.

Does **not** own scheduling, planning, inference, or memory.
"""

from __future__ import annotations

from .aggregation import ResultAggregator
from .assignment import AgentAssigner
from .builder import WorkflowBuilder
from .checkpoint import CheckpointCoordinator
from .completion import CompletionEvaluator
from .coordinator import Coordinator
from .dependency_manager import DependencyManager
from .dispatcher import Dispatcher
from .events import (
    AggregationFinished,
    BarrierReleased,
    CheckpointCreated,
    CheckpointRestored,
    EventBus,
    NodeAssigned,
    NodeCompleted,
    NodeFailed,
    OrchestratorEvent,
    RetryRequested,
    RollbackNotified,
    WorkflowCancelled,
    WorkflowCompleted,
    WorkflowCreated,
    WorkflowStarted,
)
from .exceptions import (
    AggregationError,
    AssignmentError,
    CancellationError,
    CheckpointCoordinationError,
    CoordinationError,
    InvalidWorkflowStateError,
    MetaOrchestratorError,
    ReadinessError,
    RetryCoordinationError,
    RollbackCoordinationError,
    SerializationError,
    SynchronizationError,
    ValidationError,
    WorkflowNotFoundError,
)
from .interfaces import (
    IAgentCatalogPort,
    IArmoraBudgetPort,
    ICheckpointManagerPort,
    IDashboardPort,
    IDipaHintsPort,
    IEventSink,
    IExperienceStorePort,
    IHaoeExecutionPort,
    IMetaOrchestratorPort,
    IMetricsSink,
    ISwarmContextPort,
    ITaskGraphPort,
)
from .lifecycle import WorkflowLifecycle
from .metrics import OrchestratorMetrics
from .models import (
    AgentAssignment,
    AggregatedResult,
    BudgetSlice,
    CheckpointHandle,
    ExecutionRequest,
    ExecutionSignal,
    NodeResult,
    ProgressSnapshot,
    RetryDecision,
    RollbackPlan,
    WorkflowExecution,
    WorkflowMetrics,
)
from .monitor import ExecutionMonitor
from .node_selector import NodeSelector
from .orchestrator import MetaOrchestrator, build_meta_orchestrator
from .progress import ProgressMonitor
from .readiness import ReadyNodeResolver
from .retry import RetryCoordinator
from .rollback import RollbackCoordinator
from .serializer import WorkflowSerializer, dumps, loads
from .synchronization import BarrierSynchronizer
from .validators import validate_execution
from .workflow import Workflow, bind_workflow
from .workflow_state import (
    TERMINAL_WORKFLOW_STATUSES,
    WORKFLOW_TRANSITIONS,
    WorkflowStatus,
)

__version__ = "1.0.0"

__all__ = [
    # Facade
    "MetaOrchestrator",
    "build_meta_orchestrator",
    "WorkflowBuilder",
    "Coordinator",
    "Dispatcher",
    "Workflow",
    "bind_workflow",
    # Core
    "ReadyNodeResolver",
    "DependencyManager",
    "NodeSelector",
    "AgentAssigner",
    "ResultAggregator",
    "BarrierSynchronizer",
    "WorkflowLifecycle",
    "ProgressMonitor",
    "ExecutionMonitor",
    "RetryCoordinator",
    "RollbackCoordinator",
    "CheckpointCoordinator",
    "CompletionEvaluator",
    # Models
    "WorkflowExecution",
    "WorkflowStatus",
    "AgentAssignment",
    "AggregatedResult",
    "BudgetSlice",
    "CheckpointHandle",
    "ExecutionRequest",
    "ExecutionSignal",
    "NodeResult",
    "ProgressSnapshot",
    "RetryDecision",
    "RollbackPlan",
    "WorkflowMetrics",
    "TERMINAL_WORKFLOW_STATUSES",
    "WORKFLOW_TRANSITIONS",
    # Events / metrics
    "EventBus",
    "OrchestratorEvent",
    "OrchestratorMetrics",
    "WorkflowCreated",
    "WorkflowStarted",
    "NodeAssigned",
    "NodeCompleted",
    "NodeFailed",
    "WorkflowCompleted",
    "WorkflowCancelled",
    "CheckpointCreated",
    "CheckpointRestored",
    "AggregationFinished",
    "RetryRequested",
    "RollbackNotified",
    "BarrierReleased",
    # Ports
    "ITaskGraphPort",
    "IAgentCatalogPort",
    "ISwarmContextPort",
    "IHaoeExecutionPort",
    "IArmoraBudgetPort",
    "IDipaHintsPort",
    "ICheckpointManagerPort",
    "IExperienceStorePort",
    "IDashboardPort",
    "IEventSink",
    "IMetricsSink",
    "IMetaOrchestratorPort",
    # Ser / validate
    "WorkflowSerializer",
    "dumps",
    "loads",
    "validate_execution",
    # Errors
    "MetaOrchestratorError",
    "ValidationError",
    "InvalidWorkflowStateError",
    "WorkflowNotFoundError",
    "AssignmentError",
    "CoordinationError",
    "ReadinessError",
    "SynchronizationError",
    "AggregationError",
    "CheckpointCoordinationError",
    "RetryCoordinationError",
    "RollbackCoordinationError",
    "SerializationError",
    "CancellationError",
    "__version__",
]
