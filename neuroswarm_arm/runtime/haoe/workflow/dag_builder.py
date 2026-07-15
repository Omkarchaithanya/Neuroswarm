"""DAG builder — fluent Builder pattern for TaskGraph construction."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ..interfaces.types import (
    AffinityHint,
    CorrelationIds,
    EdgeKind,
    ExecutorKind,
    PoolKind,
    PriorityClass,
    RetryPolicy,
    TaskCallable,
)
from ..core.task_graph import TaskGraph, TaskNode


class DAGBuilder:
    def __init__(self, name: str = "", ids: CorrelationIds | None = None) -> None:
        self._graph = TaskGraph(name=name, ids=ids or CorrelationIds())

    def node(
        self,
        name: str,
        fn: TaskCallable | None = None,
        *,
        pool: PoolKind = PoolKind.BACKGROUND,
        priority: PriorityClass = PriorityClass.NORMAL,
        executor: ExecutorKind = ExecutorKind.THREAD,
        retry: RetryPolicy | None = None,
        timeout_s: float | None = None,
        affinity: AffinityHint | None = None,
        is_checkpoint: bool = False,
        metadata: dict[str, Any] | None = None,
        node_id: str | None = None,
    ) -> TaskNode:
        node = TaskNode(
            node_id=node_id or __import__("uuid").uuid4().hex,
            name=name,
            fn=fn,
            pool=pool,
            priority=priority,
            executor=executor,
            retry=retry or RetryPolicy(),
            timeout_s=timeout_s,
            affinity=affinity or AffinityHint(),
            is_checkpoint=is_checkpoint,
            metadata=metadata or {},
        )
        self._graph.add_node(node)
        return node

    def edge(
        self,
        src: TaskNode | str,
        dst: TaskNode | str,
        *,
        kind: EdgeKind = EdgeKind.HARD,
        condition: Callable[[Mapping[str, Any]], bool] | None = None,
        label: str = "",
    ) -> DAGBuilder:
        self._graph.add_edge(src, dst, kind=kind, condition=condition, label=label)
        return self

    def sequence(self, *nodes: TaskNode) -> DAGBuilder:
        for a, b in zip(nodes, nodes[1:]):
            self.edge(a, b)
        return self

    def fan_out(self, src: TaskNode, *dsts: TaskNode) -> DAGBuilder:
        for d in dsts:
            self.edge(src, d, kind=EdgeKind.FAN_OUT)
        return self

    def fan_in(self, dst: TaskNode, *srcs: TaskNode) -> DAGBuilder:
        for s in srcs:
            self.edge(s, dst, kind=EdgeKind.FAN_IN)
        return self

    def context(self, **kwargs: Any) -> DAGBuilder:
        self._graph.context.update(kwargs)
        return self

    def build(self) -> TaskGraph:
        return self._graph
