"""NEXUS-ARM Swarm Context Operating System.

Shared runtime operating state every subsystem receives.

Package: ``neuroswarm_arm.runtime.swarm.context``

Canonical import::

    from neuroswarm_arm.runtime.swarm.context import SwarmContext, SwarmContextBuilder

Legacy Task Graph dataclass remains at
``neuroswarm_arm.runtime.swarm.task_graph.SwarmContext`` — bridge via adapters.
"""

from __future__ import annotations

from .budget import BudgetContext, BudgetUsage
from .builder import SwarmContextBuilder
from .cache import ContextCache
from .checkpoint import CheckpointMetadata, RestoreMetadata, create_checkpoint, restore_checkpoint
from .context import SwarmContext
from .diff import ContextDiff, FieldDiff, diff_contexts, diff_snapshots
from .events import (
    BudgetUpdated,
    CheckpointCreated,
    CheckpointRestored,
    ContextCreated,
    ContextEvent,
    ContextUpdated,
    EventBus,
    ExecutionUpdated,
    KnowledgeUpdated,
    MemoryUpdated,
    SnapshotCreated,
    SnapshotRestored,
    ToolUpdated,
)
from .exceptions import (
    BudgetError,
    CacheError,
    CheckpointError,
    InvalidReferenceError,
    MergeConflictError,
    PropagationError,
    SerializationError,
    SnapshotError,
    SwarmContextError,
    ValidationError,
    VersionMismatchError,
)
from .execution import ExecutionContext, NodeFailure, TimelineEvent
from .interfaces import (
    IAgentRegistryPort,
    IArmoraBudgetPort,
    ICheckpointManagerPort,
    IDashboardPort,
    IDipaContextPort,
    IEventSink,
    IExperienceStorePort,
    IGovernorPort,
    IHaoeContextPort,
    IMemoryRuntimePort,
    IMetaOrchestratorPort,
    IMetricsSink,
    ITaskGraphContextPort,
)
from .knowledge import KnowledgeContext, KnowledgeDocumentRef, RetrievalMeta
from .memory import CompressionMeta, MemoryContext
from .merge import (
    merge_budget,
    merge_contexts,
    merge_execution,
    merge_knowledge,
    merge_memory,
    merge_tools,
)
from .metrics import ContextMetrics
from .models import (
    ConflictPolicy,
    ContextRefKind,
    ExternalRef,
    HistoryEntry,
    RegistryHandle,
    SerializationFormat,
    TaskGraphRef,
    TelemetryContext,
)
from .propagation import (
    branch_context,
    child_context,
    fork_context,
    subgraph_context,
)
from .request import AttachmentRef, ConversationTurn, RequestContext
from .serializer import ContextSerializer, dumps, from_dict, loads, to_dict
from .snapshot import (
    SwarmContextSnapshot,
    compare_snapshots,
    create_snapshot,
    restore_snapshot,
)
from .state import MutableExecutionState
from .tools import ToolCapability, ToolContext, ToolHistoryEntry
from .tracing import TraceContext
from .validators import ValidationReport, assert_valid, validate_budget, validate_context
from .versioning import CONTEXT_SCHEMA_VERSION, assert_compatible, migrate, register_migration

__all__ = [
    # core
    "SwarmContext",
    "SwarmContextBuilder",
    "SwarmContextSnapshot",
    "CONTEXT_SCHEMA_VERSION",
    # domains
    "RequestContext",
    "AttachmentRef",
    "ConversationTurn",
    "BudgetContext",
    "BudgetUsage",
    "MemoryContext",
    "CompressionMeta",
    "KnowledgeContext",
    "KnowledgeDocumentRef",
    "RetrievalMeta",
    "ExecutionContext",
    "NodeFailure",
    "TimelineEvent",
    "ToolContext",
    "ToolCapability",
    "ToolHistoryEntry",
    "TraceContext",
    "TelemetryContext",
    "ContextMetrics",
    "MutableExecutionState",
    # models
    "ConflictPolicy",
    "SerializationFormat",
    "ContextRefKind",
    "ExternalRef",
    "RegistryHandle",
    "TaskGraphRef",
    "HistoryEntry",
    # ops
    "create_snapshot",
    "restore_snapshot",
    "compare_snapshots",
    "child_context",
    "fork_context",
    "branch_context",
    "subgraph_context",
    "merge_contexts",
    "merge_budget",
    "merge_memory",
    "merge_knowledge",
    "merge_tools",
    "merge_execution",
    "diff_contexts",
    "diff_snapshots",
    "ContextDiff",
    "FieldDiff",
    "create_checkpoint",
    "restore_checkpoint",
    "CheckpointMetadata",
    "RestoreMetadata",
    "dumps",
    "loads",
    "to_dict",
    "from_dict",
    "ContextSerializer",
    "migrate",
    "register_migration",
    "assert_compatible",
    "ContextCache",
    # validation / events
    "validate_context",
    "validate_budget",
    "assert_valid",
    "ValidationReport",
    "EventBus",
    "ContextEvent",
    "ContextCreated",
    "ContextUpdated",
    "SnapshotCreated",
    "SnapshotRestored",
    "BudgetUpdated",
    "MemoryUpdated",
    "ExecutionUpdated",
    "KnowledgeUpdated",
    "ToolUpdated",
    "CheckpointCreated",
    "CheckpointRestored",
    # interfaces
    "IArmoraBudgetPort",
    "IHaoeContextPort",
    "ITaskGraphContextPort",
    "IAgentRegistryPort",
    "IMetaOrchestratorPort",
    "IDipaContextPort",
    "IGovernorPort",
    "IMemoryRuntimePort",
    "IExperienceStorePort",
    "ICheckpointManagerPort",
    "IDashboardPort",
    "IEventSink",
    "IMetricsSink",
    # errors
    "SwarmContextError",
    "ValidationError",
    "VersionMismatchError",
    "MergeConflictError",
    "SnapshotError",
    "SerializationError",
    "PropagationError",
    "CheckpointError",
    "CacheError",
    "BudgetError",
    "InvalidReferenceError",
]

__version__ = "1.0.0"
