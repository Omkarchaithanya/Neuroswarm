"""Enums for the NEXUS-ARM Task Graph subsystem."""

from __future__ import annotations

from enum import Enum, IntEnum


class NodeType(str, Enum):
    """Logical role of a node in the workflow DAG."""

    TASK = "task"
    PARALLEL = "parallel"
    AGGREGATE = "aggregate"
    CONDITION = "condition"
    CHECKPOINT = "checkpoint"
    SUBGRAPH = "subgraph"
    AGENT = "agent"
    TOOL = "tool"
    INFERENCE = "inference"
    MEMORY = "memory"
    ROUTING = "routing"
    CUSTOM = "custom"


class EdgeKind(str, Enum):
    """Dependency edge semantics."""

    HARD = "hard"
    SOFT = "soft"
    CONDITIONAL = "conditional"
    DATA = "data"
    CONTROL = "control"
    PRIORITY = "priority"


class NodeStatus(str, Enum):
    """Mutable per-node execution status (separate from frozen graph definition)."""

    PENDING = "pending"
    QUEUED = "queued"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    RETRYING = "retrying"
    CHECKPOINTED = "checkpointed"


TERMINAL_STATUSES = frozenset(
    {
        NodeStatus.SUCCEEDED,
        NodeStatus.FAILED,
        NodeStatus.CANCELLED,
        NodeStatus.SKIPPED,
        NodeStatus.TIMED_OUT,
    }
)

SUCCESS_STATUSES = frozenset({NodeStatus.SUCCEEDED, NodeStatus.CHECKPOINTED})

NODE_TRANSITIONS: dict[NodeStatus, frozenset[NodeStatus]] = {
    NodeStatus.PENDING: frozenset(
        {NodeStatus.QUEUED, NodeStatus.READY, NodeStatus.SKIPPED, NodeStatus.CANCELLED}
    ),
    NodeStatus.QUEUED: frozenset(
        {NodeStatus.READY, NodeStatus.CANCELLED, NodeStatus.SKIPPED}
    ),
    NodeStatus.READY: frozenset(
        {NodeStatus.RUNNING, NodeStatus.CANCELLED, NodeStatus.SKIPPED, NodeStatus.QUEUED}
    ),
    NodeStatus.RUNNING: frozenset(
        {
            NodeStatus.WAITING,
            NodeStatus.SUCCEEDED,
            NodeStatus.FAILED,
            NodeStatus.CANCELLED,
            NodeStatus.TIMED_OUT,
            NodeStatus.RETRYING,
            NodeStatus.CHECKPOINTED,
        }
    ),
    NodeStatus.WAITING: frozenset(
        {
            NodeStatus.READY,
            NodeStatus.RUNNING,
            NodeStatus.CANCELLED,
            NodeStatus.FAILED,
            NodeStatus.TIMED_OUT,
        }
    ),
    NodeStatus.RETRYING: frozenset(
        {
            NodeStatus.QUEUED,
            NodeStatus.READY,
            NodeStatus.RUNNING,
            NodeStatus.FAILED,
            NodeStatus.CANCELLED,
            NodeStatus.TIMED_OUT,
        }
    ),
    NodeStatus.CHECKPOINTED: frozenset(
        {NodeStatus.SUCCEEDED, NodeStatus.READY, NodeStatus.CANCELLED}
    ),
    NodeStatus.SUCCEEDED: frozenset(),
    NodeStatus.FAILED: frozenset({NodeStatus.RETRYING}),
    NodeStatus.CANCELLED: frozenset(),
    NodeStatus.SKIPPED: frozenset(),
    NodeStatus.TIMED_OUT: frozenset({NodeStatus.RETRYING}),
}


class Priority(IntEnum):
    """Node scheduling priority. Lower value = higher urgency."""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    BACKGROUND = 3


class BackoffStrategy(str, Enum):
    CONSTANT = "constant"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


class CancelMode(str, Enum):
    NODE = "node"
    SUBTREE = "subtree"
    DOWNSTREAM = "downstream"
    GRAPH = "graph"


class CancelStyle(str, Enum):
    GRACEFUL = "graceful"
    FORCED = "forced"


class ConditionKind(str, Enum):
    ALWAYS = "always"
    NEVER = "never"
    SUCCESS = "success"
    FAILURE = "failure"
    CONFIDENCE_THRESHOLD = "confidence_threshold"
    BUDGET_THRESHOLD = "budget_threshold"
    LATENCY_THRESHOLD = "latency_threshold"
    MEMORY_THRESHOLD = "memory_threshold"
    TOOL_AVAILABILITY = "tool_availability"
    MODEL_AVAILABILITY = "model_availability"
    CUSTOM = "custom"
    AND = "and"
    OR = "or"
    NOT = "not"


class SerializationFormat(str, Enum):
    JSON = "json"
    YAML = "yaml"
    MSGPACK = "msgpack"
    PICKLE = "pickle"


class GraphPhase(str, Enum):
    """Whole-graph execution phase."""

    IDLE = "idle"
    VALIDATING = "validating"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
