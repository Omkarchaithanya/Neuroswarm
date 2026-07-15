"""Workflow scheduler — plans + dispatches named workflows."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ..core.dispatcher import Dispatcher
from ..execution.execution_context import ExecutionContext
from ..interfaces.types import CorrelationIds, PoolKind, PriorityClass
from ..workflow.planner import WorkflowPlanner
from ..workflow.workflow_executor import WorkflowResult


class WorkflowScheduler:
    def __init__(
        self,
        planner: WorkflowPlanner,
        dispatcher: Dispatcher,
    ) -> None:
        self.planner = planner
        self.dispatcher = dispatcher

    def submit_chat(
        self,
        handlers: Mapping[str, Callable[[ExecutionContext], Any]],
        *,
        ids: CorrelationIds | None = None,
        context: dict[str, Any] | None = None,
        numa_node: int | None = None,
        ctx: ExecutionContext | None = None,
    ) -> WorkflowResult:
        graph = self.planner.plan_chat(
            handlers, ids=ids, context=context, numa_node=numa_node
        )
        return self.dispatcher.execute_graph(graph, ctx=ctx)

    def submit_multi_agent(
        self,
        handlers: Mapping[str, Callable[[ExecutionContext], Any]],
        *,
        ids: CorrelationIds | None = None,
        context: dict[str, Any] | None = None,
        ctx: ExecutionContext | None = None,
    ) -> WorkflowResult:
        graph = self.planner.plan_multi_agent(handlers, ids=ids, context=context)
        return self.dispatcher.execute_graph(graph, ctx=ctx)

    def submit_callable(
        self,
        fn: Callable[..., Any],
        *,
        priority: PriorityClass = PriorityClass.NORMAL,
        numa_node: int | None = None,
        name: str = "task",
    ) -> Any:
        def _wrap(ctx: ExecutionContext) -> Any:
            try:
                return fn(ctx)
            except TypeError:
                return fn()

        pool = (
            PoolKind.INFERENCE
            if priority <= PriorityClass.HIGH
            else PoolKind.BACKGROUND
        )
        graph = self.planner.plan_single(
            _wrap,
            name=name,
            priority=priority,
            numa_node=numa_node,
            pool=pool,
        )
        result = self.dispatcher.execute_graph(graph)
        return result.output
