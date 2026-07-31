"""Workflow planner — builds standard agent / chat DAGs."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ..core.task_graph import TaskGraph
from ..execution.execution_context import ExecutionContext
from ..interfaces.types import (
    CorrelationIds,
    ExecutorKind,
    PoolKind,
    PriorityClass,
    RetryPolicy,
)
from .dag_builder import DAGBuilder


ChatHandlers = Mapping[str, Callable[[ExecutionContext], Any]]


class WorkflowPlanner:
    """Constructs named workflow templates. Handlers are injected (no inference imports)."""

    def plan_chat(
        self,
        handlers: ChatHandlers,
        *,
        ids: CorrelationIds | None = None,
        context: dict[str, Any] | None = None,
        numa_node: int | None = None,
    ) -> TaskGraph:
        """
        Default chat workflow:

        mem0_recall → okf_context → semantic_route → tool_search_activation
        → okf_tool_docs → kv_session → cascade → kv_checkpoint → response

        Mem0 = facts only. OKF = institutional knowledge. Tool docs load after route.
        tool_search_activation may replace schemas with Hermes bridge tool.
        """
        ids = ids or CorrelationIds()
        b = DAGBuilder(name="chat", ids=ids)
        if context:
            b.context(**context)

        def _passthrough(name: str):
            """Optional node: no-op when handler absent (backward compatible)."""
            handler = handlers.get(name)
            if handler is not None:
                return handler

            def _noop(ctx: ExecutionContext) -> None:
                return None

            return _noop

        mem0 = b.node(
            "mem0_recall",
            _passthrough("mem0_recall"),
            pool=PoolKind.MEMORY,
            priority=PriorityClass.HIGH,
            executor=ExecutorKind.THREAD,
            metadata={"stage": "mem0"},
        )
        okf_ctx = b.node(
            "okf_context",
            _passthrough("okf_context"),
            pool=PoolKind.MEMORY,
            priority=PriorityClass.HIGH,
            executor=ExecutorKind.THREAD,
            metadata={"stage": "okf"},
        )
        route = b.node(
            "semantic_route",
            handlers.get("semantic_route"),
            pool=PoolKind.EMBEDDING,
            priority=PriorityClass.HIGH,
            executor=ExecutorKind.THREAD,
            metadata={"stage": "route"},
        )
        tool_search = b.node(
            "tool_search_activation",
            _passthrough("tool_search_activation"),
            pool=PoolKind.EMBEDDING,
            priority=PriorityClass.HIGH,
            executor=ExecutorKind.THREAD,
            metadata={"stage": "tool_search"},
        )
        okf_tools = b.node(
            "okf_tool_docs",
            _passthrough("okf_tool_docs"),
            pool=PoolKind.MEMORY,
            priority=PriorityClass.HIGH,
            executor=ExecutorKind.THREAD,
            metadata={"stage": "okf_tools"},
        )
        kv_session = b.node(
            "kv_session",
            handlers.get("kv_session"),
            pool=PoolKind.MEMORY,
            priority=PriorityClass.HIGH,
            executor=ExecutorKind.THREAD,
            is_checkpoint=True,
            metadata={"stage": "memory"},
        )
        cascade = b.node(
            "cascade",
            handlers.get("cascade"),
            pool=PoolKind.INFERENCE,
            priority=PriorityClass.CRITICAL,
            executor=ExecutorKind.THREAD,
            retry=RetryPolicy(max_attempts=2, backoff_base_s=0.02),
            metadata={"stage": "inference"},
        )
        kv_ckpt = b.node(
            "kv_checkpoint",
            handlers.get("kv_checkpoint"),
            pool=PoolKind.MEMORY,
            priority=PriorityClass.NORMAL,
            executor=ExecutorKind.THREAD,
            is_checkpoint=True,
            metadata={"stage": "memory"},
        )
        response = b.node(
            "response",
            handlers.get("response"),
            pool=PoolKind.PLANNER,
            priority=PriorityClass.HIGH,
            executor=ExecutorKind.INLINE,
            metadata={"stage": "aggregate"},
        )
        b.sequence(
            mem0,
            okf_ctx,
            route,
            tool_search,
            okf_tools,
            kv_session,
            cascade,
            kv_ckpt,
            response,
        )
        if numa_node is not None:
            for node in (
                mem0,
                okf_ctx,
                route,
                tool_search,
                okf_tools,
                kv_session,
                cascade,
                kv_ckpt,
                response,
            ):
                node.affinity.numa_node = numa_node
        return b.build()

    def plan_multi_agent(
        self,
        handlers: ChatHandlers,
        *,
        ids: CorrelationIds | None = None,
        context: dict[str, Any] | None = None,
    ) -> TaskGraph:
        """
        planner → research → memory → reason → tool → review → aggregate → stream
        """
        ids = ids or CorrelationIds()
        b = DAGBuilder(name="multi_agent", ids=ids)
        if context:
            b.context(**context)

        def n(name: str, pool: PoolKind, pri: PriorityClass = PriorityClass.NORMAL):
            return b.node(
                name,
                handlers.get(name),
                pool=pool,
                priority=pri,
                executor=ExecutorKind.THREAD,
                metadata={"agent": name},
            )

        planner = n("planner", PoolKind.PLANNER, PriorityClass.HIGH)
        research = n("research", PoolKind.TOOL, PriorityClass.NORMAL)
        memory = n("memory", PoolKind.MEMORY, PriorityClass.NORMAL)
        reason = n("reason", PoolKind.INFERENCE, PriorityClass.CRITICAL)
        tool = n("tool", PoolKind.TOOL, PriorityClass.HIGH)
        review = n("review", PoolKind.INFERENCE, PriorityClass.HIGH)
        aggregate = n("aggregate", PoolKind.PLANNER, PriorityClass.HIGH)
        stream = n("stream", PoolKind.TELEMETRY, PriorityClass.NORMAL)

        b.sequence(planner, research, memory, reason, tool, review, aggregate, stream)
        return b.build()

    def plan_single(
        self,
        fn: Callable[[ExecutionContext], Any],
        *,
        name: str = "task",
        ids: CorrelationIds | None = None,
        pool: PoolKind = PoolKind.BACKGROUND,
        priority: PriorityClass = PriorityClass.NORMAL,
        numa_node: int | None = None,
    ) -> TaskGraph:
        """Compatibility path for HAOEScheduler.schedule(callable)."""
        b = DAGBuilder(name=name, ids=ids or CorrelationIds())
        node = b.node(
            name,
            fn,
            pool=pool,
            priority=priority,
            executor=ExecutorKind.INLINE,
        )
        if numa_node is not None:
            node.affinity.numa_node = numa_node
        return b.build()
