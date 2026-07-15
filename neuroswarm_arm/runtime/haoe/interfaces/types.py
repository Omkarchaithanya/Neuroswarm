"""Shared enums and value types for the HAOE runtime kernel.

Architectural note: these types are the vocabulary of the agent runtime.
Higher layers (gateway, cascade, KV) speak this vocabulary through protocols;
HAOE never imports inference or memory implementations directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Callable, Mapping
from uuid import uuid4


class PriorityClass(IntEnum):
    """Scheduler priority bands. Lower numeric value = higher urgency."""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    BACKGROUND = 3


class TaskState(str, Enum):
    """Task lifecycle state machine (runtime kernel, not OS threads)."""

    QUEUED = "queued"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING = "waiting"
    RETRY = "retry"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


TERMINAL_STATES = frozenset(
    {TaskState.CANCELLED, TaskState.COMPLETED, TaskState.FAILED}
)

# Legal transitions for the task state machine.
TASK_TRANSITIONS: Mapping[TaskState, frozenset[TaskState]] = {
    TaskState.QUEUED: frozenset({TaskState.READY, TaskState.CANCELLED}),
    TaskState.READY: frozenset(
        {TaskState.RUNNING, TaskState.CANCELLED, TaskState.QUEUED}
    ),
    TaskState.RUNNING: frozenset(
        {
            TaskState.PAUSED,
            TaskState.WAITING,
            TaskState.RETRY,
            TaskState.CANCELLED,
            TaskState.COMPLETED,
            TaskState.FAILED,
        }
    ),
    TaskState.PAUSED: frozenset(
        {TaskState.READY, TaskState.RUNNING, TaskState.CANCELLED}
    ),
    TaskState.WAITING: frozenset(
        {TaskState.READY, TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED}
    ),
    TaskState.RETRY: frozenset(
        {TaskState.QUEUED, TaskState.READY, TaskState.CANCELLED, TaskState.FAILED}
    ),
    TaskState.CANCELLED: frozenset(),
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset({TaskState.RETRY}),
}


class EdgeKind(str, Enum):
    """Dependency edge semantics in the task graph."""

    HARD = "hard"
    CONDITIONAL = "conditional"
    FAN_OUT = "fan_out"
    FAN_IN = "fan_in"
    CHECKPOINT = "checkpoint"
    RETRY = "retry"
    CANCEL = "cancel"


class PoolKind(str, Enum):
    """Independently scalable worker pool kinds."""

    INFERENCE = "inference"
    MEMORY = "memory"
    EMBEDDING = "embedding"
    TOOL = "tool"
    PLANNER = "planner"
    BACKGROUND = "background"
    TELEMETRY = "telemetry"
    MAINTENANCE = "maintenance"


class ExecutorKind(str, Enum):
    """Execution backend selection."""

    ASYNC = "async"
    THREAD = "thread"
    PROCESS = "process"
    NATIVE = "native"  # future Rust / C extension scheduler
    INLINE = "inline"  # tests / single-node fallback


class FeatureStatus(str, Enum):
    """Hardware feature availability (never hard-fail on Axion)."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    EMULATED = "emulated"


class RuntimePhase(str, Enum):
    """HAOE kernel lifecycle."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    DRAINING = "draining"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(slots=True)
class CorrelationIds:
    """Every unit of work carries full correlation for observability."""

    trace_id: str = field(default_factory=lambda: uuid4().hex)
    workflow_id: str = field(default_factory=lambda: uuid4().hex)
    request_id: str = field(default_factory=lambda: uuid4().hex)
    agent_id: str = ""
    execution_id: str = field(default_factory=lambda: uuid4().hex)
    correlation_id: str = field(default_factory=lambda: uuid4().hex)

    def child(self, *, agent_id: str | None = None) -> CorrelationIds:
        return CorrelationIds(
            trace_id=self.trace_id,
            workflow_id=self.workflow_id,
            request_id=self.request_id,
            agent_id=agent_id if agent_id is not None else self.agent_id,
            execution_id=uuid4().hex,
            correlation_id=self.correlation_id,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "trace_id": self.trace_id,
            "workflow_id": self.workflow_id,
            "request_id": self.request_id,
            "agent_id": self.agent_id,
            "execution_id": self.execution_id,
            "correlation_id": self.correlation_id,
        }


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_base_s: float = 0.05
    backoff_factor: float = 2.0
    backoff_max_s: float = 5.0
    retryable_exceptions: tuple[type[BaseException], ...] = (Exception,)

    def delay_for(self, attempt: int) -> float:
        """Exponential backoff capped at backoff_max_s (attempt is 0-based)."""
        delay = self.backoff_base_s * (self.backoff_factor**attempt)
        return min(delay, self.backoff_max_s)


@dataclass(slots=True)
class ResourceEstimate:
    """Cost model inputs for cost-aware scheduling."""

    cpu_cost: float = 1.0
    memory_bytes: int = 0
    kv_pressure: float = 0.0
    expected_latency_ms: float = 0.0
    queue_length: int = 0
    task_weight: float = 1.0
    agent_weight: float = 1.0
    model_warmness: float = 0.5
    scheduling_confidence: float = 1.0

    def score(self) -> float:
        """Higher score = more expensive / prefer dedicated capacity."""
        return (
            self.cpu_cost * self.task_weight * self.agent_weight
            + self.kv_pressure * 2.0
            + (self.expected_latency_ms / 1000.0)
            + (1.0 - self.model_warmness)
        )


@dataclass(slots=True)
class AffinityHint:
    """Soft placement hint — never a hard NUMA requirement on Axion."""

    preferred_cores: list[int] = field(default_factory=list)
    numa_node: int | None = None
    locality_tag: str = ""
    pin: bool = False


TaskCallable = Callable[..., Any]
