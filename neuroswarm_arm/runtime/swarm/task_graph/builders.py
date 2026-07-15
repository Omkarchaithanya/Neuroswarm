"""Fluent TaskGraphBuilder API."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from .edge import TaskEdge
from .enums import EdgeKind, NodeType, Priority
from .graph import TaskGraph
from .models import RetryPolicy, TimeoutPolicy
from .node import TaskNode
from .utils import new_id


class TaskGraphBuilder:
    """
    Example::

        graph = (
            TaskGraphBuilder()
            .task("research", ...)
            .parallel("plan", "memory")
            .aggregate("join")
            .retry(max_attempts=3)
            .timeout(30.0)
            .build()
        )
    """

    def __init__(self, name: str = "", **meta: Any) -> None:
        self._graph = TaskGraph(name=name, metadata=dict(meta))
        self._last: list[str] = []
        self._pending_retry: RetryPolicy | None = None
        self._pending_timeout: float | None = None
        self._pending_condition: dict[str, Any] | None = None
        self._group_stack: list[list[str]] = []

    def task(
        self,
        name: str,
        *,
        node_id: str | None = None,
        node_type: NodeType = NodeType.TASK,
        agent_type: str = "",
        priority: Priority = Priority.NORMAL,
        handler_key: str | None = None,
        estimated_latency: float = 0.0,
        estimated_cost: float = 0.0,
        memory_requirement: int = 0,
        required_tools: Sequence[str] | None = None,
        required_models: Sequence[str] | None = None,
        tags: Sequence[str] | None = None,
        metadata: dict[str, Any] | None = None,
        depends_on: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> TaskGraphBuilder:
        node = TaskNode(
            id=node_id or new_id("n_"),
            name=name,
            display_name=kwargs.pop("display_name", name),
            description=kwargs.pop("description", ""),
            agent_type=agent_type,
            node_type=node_type,
            priority=priority,
            handler_key=handler_key or name,
            estimated_latency=estimated_latency,
            estimated_cost=estimated_cost,
            memory_requirement=memory_requirement,
            required_tools=list(required_tools or []),
            required_models=list(required_models or []),
            tags=list(tags or []),
            metadata=metadata or {},
            retry_policy=self._pending_retry or RetryPolicy(),
            timeout=self._pending_timeout,
            condition=self._pending_condition,
            **kwargs,
        )
        self._graph.add_node(node)
        preds: list[str]
        if depends_on is not None:
            preds = list(depends_on)
        else:
            preds = list(self._last)
        for pred in preds:
            if pred in self._graph.nodes:
                self._graph.add_edge(pred, node.id, kind=EdgeKind.HARD)
        self._last = [node.id]
        self._pending_retry = None
        self._pending_timeout = None
        self._pending_condition = None
        return self

    def parallel(self, *names: str, **common: Any) -> TaskGraphBuilder:
        """Fan-out: each name depends on previous ``_last`` set; becomes new ``_last``."""
        preds = list(self._last)
        created: list[str] = []
        for name in names:
            node = TaskNode(
                id=new_id("n_"),
                name=name,
                display_name=name,
                node_type=NodeType.PARALLEL,
                handler_key=common.get("handler_key", name),
                agent_type=common.get("agent_type", ""),
                priority=common.get("priority", Priority.NORMAL),
                estimated_latency=common.get("estimated_latency", 0.0),
                estimated_cost=common.get("estimated_cost", 0.0),
                retry_policy=self._pending_retry or RetryPolicy(),
                timeout=self._pending_timeout,
                condition=self._pending_condition,
                metadata=dict(common.get("metadata") or {}),
            )
            self._graph.add_node(node)
            for pred in preds:
                if pred in self._graph.nodes:
                    self._graph.add_edge(pred, node.id, kind=EdgeKind.HARD)
            created.append(node.id)
        self._last = created
        self._pending_retry = None
        self._pending_timeout = None
        self._pending_condition = None
        return self

    def aggregate(
        self,
        name: str = "aggregate",
        *,
        from_nodes: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> TaskGraphBuilder:
        preds = list(from_nodes) if from_nodes is not None else list(self._last)
        node = TaskNode(
            id=kwargs.pop("node_id", None) or new_id("n_"),
            name=name,
            display_name=kwargs.pop("display_name", name),
            node_type=NodeType.AGGREGATE,
            handler_key=kwargs.pop("handler_key", name),
            retry_policy=self._pending_retry or RetryPolicy(),
            timeout=self._pending_timeout,
            condition=self._pending_condition,
            **kwargs,
        )
        self._graph.add_node(node)
        for pred in preds:
            if pred in self._graph.nodes:
                self._graph.add_edge(pred, node.id, kind=EdgeKind.HARD)
        self._last = [node.id]
        self._pending_retry = None
        self._pending_timeout = None
        self._pending_condition = None
        return self

    def condition(self, condition: dict[str, Any] | Any) -> TaskGraphBuilder:
        if hasattr(condition, "to_dict"):
            self._pending_condition = condition.to_dict()
        else:
            self._pending_condition = dict(condition)
        return self

    def retry(
        self,
        max_attempts: int = 3,
        *,
        policy: RetryPolicy | None = None,
        **kwargs: Any,
    ) -> TaskGraphBuilder:
        if policy is not None:
            self._pending_retry = policy
        else:
            self._pending_retry = RetryPolicy(max_attempts=max_attempts, **kwargs)
        return self

    def timeout(self, seconds: float) -> TaskGraphBuilder:
        self._pending_timeout = seconds
        return self

    def workflow_timeout(self, seconds: float) -> TaskGraphBuilder:
        self._graph.timeout_policy = TimeoutPolicy(
            node_timeout_s=self._graph.timeout_policy.node_timeout_s,
            subgraph_timeout_s=self._graph.timeout_policy.subgraph_timeout_s,
            workflow_timeout_s=seconds,
        )
        return self

    def edge(
        self,
        src: str,
        dst: str,
        *,
        kind: EdgeKind = EdgeKind.HARD,
        **kwargs: Any,
    ) -> TaskGraphBuilder:
        src_id = self._resolve(src)
        dst_id = self._resolve(dst)
        self._graph.add_edge(src_id, dst_id, kind=kind, **kwargs)
        return self

    def meta(self, **metadata: Any) -> TaskGraphBuilder:
        self._graph.metadata.update(metadata)
        return self

    def tag(self, *tags: str) -> TaskGraphBuilder:
        self._graph.tags.extend(tags)
        return self

    def _resolve(self, name_or_id: str) -> str:
        if name_or_id in self._graph.nodes:
            return name_or_id
        for nid, node in self._graph.nodes.items():
            if node.name == name_or_id:
                return nid
        raise KeyError(f"unknown node: {name_or_id}")

    def build(self, *, freeze: bool = True, validate: bool = True) -> TaskGraph:
        g = self._graph
        g._sync_dep_links()
        if validate:
            from .validator import validate_graph

            validate_graph(g, raise_on_error=True)
        if freeze:
            g.freeze()
        return g

    @property
    def graph(self) -> TaskGraph:
        return self._graph
