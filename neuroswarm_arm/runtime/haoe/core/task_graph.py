"""Task graph model — DAG of agent/runtime work units.

Every API request becomes a TaskGraph. HAOE never reduces a request to a
single unstructured coroutine at the kernel boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from uuid import uuid4

from ..interfaces.types import (
    AffinityHint,
    CorrelationIds,
    EdgeKind,
    ExecutorKind,
    PoolKind,
    PriorityClass,
    ResourceEstimate,
    RetryPolicy,
    TaskCallable,
    TaskState,
)
from ..runtime.runtime_state import TaskStateMachine


@dataclass
class TaskNode:
    """A single schedulable unit in the graph."""

    node_id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    fn: TaskCallable | None = None
    pool: PoolKind = PoolKind.BACKGROUND
    priority: PriorityClass = PriorityClass.NORMAL
    executor: ExecutorKind = ExecutorKind.THREAD
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_s: float | None = None
    affinity: AffinityHint = field(default_factory=AffinityHint)
    estimate: ResourceEstimate = field(default_factory=ResourceEstimate)
    metadata: dict[str, Any] = field(default_factory=dict)
    # Conditional edge predicate result key in workflow context
    condition_key: str | None = None
    is_checkpoint: bool = False
    sm: TaskStateMachine = field(default_factory=TaskStateMachine)
    result: Any = None
    error: BaseException | None = None
    attempts: int = 0

    @property
    def state(self) -> TaskState:
        return self.sm.state


@dataclass(slots=True)
class TaskEdge:
    src: str
    dst: str
    kind: EdgeKind = EdgeKind.HARD
    condition: Callable[[Mapping[str, Any]], bool] | None = None
    label: str = ""


@dataclass
class TaskGraph:
    graph_id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    nodes: dict[str, TaskNode] = field(default_factory=dict)
    edges: list[TaskEdge] = field(default_factory=list)
    ids: CorrelationIds = field(default_factory=CorrelationIds)
    context: dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: TaskNode) -> TaskNode:
        self.nodes[node.node_id] = node
        return node

    def add_edge(
        self,
        src: str | TaskNode,
        dst: str | TaskNode,
        *,
        kind: EdgeKind = EdgeKind.HARD,
        condition: Callable[[Mapping[str, Any]], bool] | None = None,
        label: str = "",
    ) -> TaskEdge:
        src_id = src.node_id if isinstance(src, TaskNode) else src
        dst_id = dst.node_id if isinstance(dst, TaskNode) else dst
        edge = TaskEdge(src=src_id, dst=dst_id, kind=kind, condition=condition, label=label)
        self.edges.append(edge)
        return edge

    def successors(self, node_id: str) -> list[str]:
        return [e.dst for e in self.edges if e.src == node_id]

    def predecessors(self, node_id: str) -> list[str]:
        return [e.src for e in self.edges if e.dst == node_id]

    def edges_from(self, node_id: str) -> list[TaskEdge]:
        return [e for e in self.edges if e.src == node_id]
