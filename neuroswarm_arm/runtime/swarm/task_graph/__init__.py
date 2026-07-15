"""NEXUS-ARM Task Graph — production DAG representation for HAOE.

Public API for ``neuroswarm_arm.runtime.swarm.task_graph``.
"""

from __future__ import annotations

from .builders import TaskGraphBuilder
from .conditions import (
    Always,
    And,
    BudgetThreshold,
    ConfidenceThreshold,
    Custom,
    Failure,
    LatencyThreshold,
    MemoryThreshold,
    ModelAvailability,
    Never,
    Not,
    Or,
    Success,
    ToolAvailability,
    condition_from_dict,
    evaluate_condition,
    register_condition,
)
from .context import (
    BudgetContext,
    ExecutionContext,
    MemoryContext,
    SwarmContext,
    TracingContext,
)
from .dag import DAGAnalyzer
from .edge import TaskEdge
from .enums import (
    BackoffStrategy,
    CancelMode,
    CancelStyle,
    ConditionKind,
    EdgeKind,
    GraphPhase,
    NodeStatus,
    NodeType,
    Priority,
    SerializationFormat,
)
from .events import EventBus, TaskGraphEvent
from .exceptions import (
    CancellationError,
    CycleError,
    FrozenGraphError,
    TaskGraphError,
    ValidationError,
)
from .executor import ExecutionResult, ExecutionState, GraphExecutor
from .graph import TaskGraph
from .metrics import GraphMetrics, compute_static_metrics
from .models import (
    Budget,
    GraphMeta,
    RetryPolicy,
    TimeoutPolicy,
    ValidationReport,
)
from .node import TaskNode
from .planner import WorkflowPlanner
from .serializer import GraphSerializer, dumps, loads
from .validator import GraphValidator, validate_graph
from .visualization import to_ascii, to_dot, to_json_graph, to_mermaid

__all__ = [
    # core
    "TaskGraph",
    "TaskNode",
    "TaskEdge",
    "DAGAnalyzer",
    "TaskGraphBuilder",
    "WorkflowPlanner",
    # execution
    "GraphExecutor",
    "ExecutionState",
    "ExecutionResult",
    # validation / ser
    "GraphValidator",
    "validate_graph",
    "ValidationReport",
    "GraphSerializer",
    "dumps",
    "loads",
    # conditions
    "Always",
    "Never",
    "Success",
    "Failure",
    "ConfidenceThreshold",
    "BudgetThreshold",
    "LatencyThreshold",
    "MemoryThreshold",
    "ToolAvailability",
    "ModelAvailability",
    "Custom",
    "And",
    "Or",
    "Not",
    "condition_from_dict",
    "evaluate_condition",
    "register_condition",
    # context
    "SwarmContext",
    "ExecutionContext",
    "MemoryContext",
    "BudgetContext",
    "TracingContext",
    # enums / models
    "NodeType",
    "EdgeKind",
    "NodeStatus",
    "Priority",
    "BackoffStrategy",
    "CancelMode",
    "CancelStyle",
    "ConditionKind",
    "GraphPhase",
    "SerializationFormat",
    "RetryPolicy",
    "Budget",
    "TimeoutPolicy",
    "GraphMeta",
    # events / metrics / viz
    "EventBus",
    "TaskGraphEvent",
    "GraphMetrics",
    "compute_static_metrics",
    "to_mermaid",
    "to_dot",
    "to_ascii",
    "to_json_graph",
    # errors
    "TaskGraphError",
    "ValidationError",
    "CycleError",
    "FrozenGraphError",
    "CancellationError",
]

__version__ = "1.0.0"
