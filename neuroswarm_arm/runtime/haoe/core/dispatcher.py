"""Dispatcher — Mediator between scheduler admission and task execution."""

from __future__ import annotations

from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from ..core.task_graph import TaskGraph
from ..execution.execution_context import ExecutionContext
from ..execution.task_executor import TaskExecutor
from ..interfaces.types import AffinityHint, PoolKind, PriorityClass, ResourceEstimate
from ..scheduling.priority_scheduler import PriorityScheduler
from ..scheduling.queue_manager import QueuedTask
from ..scheduling.resource_allocator import ResourceAllocator
from ..workflow.workflow_executor import WorkflowExecutor, WorkflowResult


class Dispatcher:
    """
    Mediator: submit graphs for immediate execution (deterministic path) or
    enqueue individual tasks onto worker pools (async path).

    Chat/gateway uses execute_graph() for correctness and latency predictability.
    Background/maintenance work can use enqueue().
    """

    def __init__(
        self,
        scheduler: PriorityScheduler,
        allocator: ResourceAllocator,
        task_executor: TaskExecutor,
        workflow_executor: WorkflowExecutor,
        *,
        on_complete: Callable[[QueuedTask, Any], None] | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._allocator = allocator
        self._tasks = task_executor
        self._workflows = workflow_executor
        self._on_complete = on_complete
        self._pending: dict[str, QueuedTask] = {}

    def execute_graph(
        self,
        graph: TaskGraph,
        *,
        ctx: ExecutionContext | None = None,
    ) -> WorkflowResult:
        return self._workflows.execute(graph, parent_ctx=ctx)

    def enqueue(
        self,
        task_id: str | None = None,
        *,
        payload: Any,
        pool: PoolKind = PoolKind.BACKGROUND,
        priority: PriorityClass = PriorityClass.NORMAL,
        affinity: AffinityHint | None = None,
        estimate: ResourceEstimate | None = None,
    ) -> str:
        tid = task_id or uuid4().hex
        alloc = self._allocator.allocate(
            pool=pool,
            priority=priority,
            numa_node=affinity.numa_node if affinity else None,
            locality_tag=affinity.locality_tag if affinity else "",
            pin=affinity.pin if affinity else False,
        )
        self._scheduler.submit(
            tid,
            priority=alloc.priority,
            pool=alloc.pool,
            estimate=estimate or alloc.estimate,
            affinity=affinity or alloc.affinity,
            payload=payload,
        )
        return tid

    def handle_queued_task(self, task: QueuedTask) -> None:
        """Worker-pool callback: run payload if it is a callable."""
        start = monotonic()
        result: Any = None
        try:
            payload = task.payload
            if callable(payload):
                ctx = ExecutionContext()
                ctx.numa_node = task.affinity.numa_node
                result = payload(ctx) if _accepts_ctx(payload) else payload()
        finally:
            if self._on_complete is not None:
                self._on_complete(task, result)
            _ = start  # reserved for latency metrics hook


def _accepts_ctx(fn: Callable[..., Any]) -> bool:
    try:
        import inspect

        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        return bool(params)
    except (TypeError, ValueError):
        return False
