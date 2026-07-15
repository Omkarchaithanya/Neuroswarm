"""Core executor facade over TaskExecutor + WorkflowExecutor."""

from __future__ import annotations

from typing import Any

from ..core.task_graph import TaskGraph
from ..execution.execution_context import ExecutionContext
from ..execution.task_executor import TaskExecutor
from ..workflow.workflow_executor import WorkflowExecutor, WorkflowResult


class HAOEExecutor:
    def __init__(
        self,
        task_executor: TaskExecutor,
        workflow_executor: WorkflowExecutor,
    ) -> None:
        self.tasks = task_executor
        self.workflows = workflow_executor

    def run_graph(self, graph: TaskGraph, ctx: ExecutionContext | None = None) -> WorkflowResult:
        return self.workflows.execute(graph, parent_ctx=ctx)

    def run_node(self, node: Any, ctx: ExecutionContext) -> Any:
        return self.tasks.execute(node, ctx)

    def shutdown(self) -> None:
        self.tasks.shutdown()
