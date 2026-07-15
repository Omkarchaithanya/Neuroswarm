"""Workflow executor — drives TaskGraph to completion."""

from __future__ import annotations

from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from ..core.task_graph import TaskGraph, TaskNode
from ..execution.execution_context import ExecutionContext
from ..execution.task_executor import TaskExecutor
from ..interfaces.types import CorrelationIds, TaskState, TERMINAL_STATES
from ..runtime.runtime_events import task_event, workflow_event
from ..telemetry.event_bus import EventBus
from .cancellation import CancellationManager, CancellationToken, CancelledError
from .checkpointing import CheckpointStore
from .dependency_graph import DependencyGraph
from .retry_manager import RetryManager


class WorkflowResult:
    def __init__(self, graph: TaskGraph) -> None:
        self.graph = graph
        self.results: dict[str, Any] = {
            nid: n.result for nid, n in graph.nodes.items()
        }
        self.errors: dict[str, BaseException] = {
            nid: n.error for nid, n in graph.nodes.items() if n.error is not None
        }
        self.completed = all(n.state is TaskState.COMPLETED for n in graph.nodes.values())
        self.cancelled = any(n.state is TaskState.CANCELLED for n in graph.nodes.values())
        self.failed = any(n.state is TaskState.FAILED for n in graph.nodes.values())

    @property
    def output(self) -> Any:
        # Prefer node named "response" / last completed in topo sense
        for preferred in ("response", "aggregate", "cascade", "output"):
            for node in self.graph.nodes.values():
                if node.name == preferred and node.state is TaskState.COMPLETED:
                    return node.result
        for node in self.graph.nodes.values():
            if node.state is TaskState.COMPLETED and node.result is not None:
                return node.result
        return None


class WorkflowExecutor:
    def __init__(
        self,
        task_executor: TaskExecutor,
        *,
        checkpoints: CheckpointStore | None = None,
        cancellations: CancellationManager | None = None,
        event_bus: EventBus | None = None,
        retry_manager: RetryManager | None = None,
    ) -> None:
        self._tasks = task_executor
        self._checkpoints = checkpoints
        self._cancel = cancellations or CancellationManager()
        self._bus = event_bus
        self._retry = retry_manager or RetryManager()

    def execute(
        self,
        graph: TaskGraph,
        *,
        parent_ctx: ExecutionContext | None = None,
        token: CancellationToken | None = None,
    ) -> WorkflowResult:
        dep = DependencyGraph(graph)
        if not dep.is_dag():
            raise ValueError(f"workflow {graph.graph_id} is not a DAG")
        dep.inherit_priorities()

        ids = graph.ids
        cancel = token or self._cancel.create(graph.graph_id)
        base_ctx = parent_ctx or ExecutionContext(ids=ids, cancellation=cancel)
        if parent_ctx is None:
            base_ctx.cancellation = cancel

        self._publish(
            workflow_event(
                "workflow_started",
                workflow_id=graph.graph_id,
                ids=ids,
                workflow_name=graph.name,
            )
        )

        completed: set[str] = set()
        start = monotonic()

        # Resume from checkpoints if present
        if self._checkpoints is not None:
            for nid in self._checkpoints.list_nodes(graph.graph_id):
                node = graph.nodes.get(nid)
                if node is None:
                    continue
                data = self._checkpoints.load(graph.graph_id, nid)
                if data is not None:
                    node.result = data.get("payload", {}).get("result")
                    node.sm.force(TaskState.COMPLETED)
                    completed.add(nid)

        try:
            while len(completed) < len(graph.nodes):
                if cancel.is_cancelled():
                    for nid, node in graph.nodes.items():
                        if nid not in completed and node.state not in TERMINAL_STATES:
                            node.sm.force(TaskState.CANCELLED)
                    raise CancelledError(f"workflow {graph.graph_id} cancelled")

                ready = [nid for nid in dep.ready_nodes(completed) if nid not in completed]
                if not ready:
                    # Deadlock / conditional skip — mark unreachable as cancelled
                    for nid, node in graph.nodes.items():
                        if nid not in completed and node.state not in TERMINAL_STATES:
                            node.sm.force(TaskState.CANCELLED)
                    break

                # Execute ready nodes sequentially for deterministic chat path;
                # fan-out parallelism is expressed by submitting multiple ready nodes —
                # we run them one-by-one here for safety; dispatcher may parallelize later.
                for nid in ready:
                    node = graph.nodes[nid]
                    if node.sm.state is TaskState.QUEUED:
                        node.sm.transition(TaskState.READY)
                    ctx = base_ctx.child(agent_id=node.metadata.get("agent_id"))
                    ctx.baggage.update(graph.context)
                    self._publish(
                        task_event(
                            "task_started",
                            task_id=nid,
                            state=node.state,
                            ids=ctx.ids,
                            name=node.name,
                        )
                    )
                    try:
                        result = self._tasks.execute(node, ctx)
                        graph.context[f"result:{node.name}"] = result
                        graph.context[f"result:{nid}"] = result
                        if node.is_checkpoint and self._checkpoints is not None:
                            self._checkpoints.save(
                                graph.graph_id,
                                nid,
                                {"result": result, "name": node.name},
                            )
                        completed.add(nid)
                        self._publish(
                            task_event(
                                "task_completed",
                                task_id=nid,
                                state=node.state,
                                ids=ctx.ids,
                                name=node.name,
                            )
                        )
                    except CancelledError:
                        completed.add(nid)
                        self._publish(
                            task_event(
                                "task_cancelled",
                                task_id=nid,
                                state=node.state,
                                ids=ctx.ids,
                                name=node.name,
                            )
                        )
                        raise
                    except Exception as exc:
                        completed.add(nid)
                        self._publish(
                            task_event(
                                "task_failed",
                                task_id=nid,
                                state=node.state,
                                ids=ctx.ids,
                                name=node.name,
                                error=str(exc),
                            )
                        )
                        # Fail-fast for chat workflows
                        raise

        finally:
            self._cancel.discard(graph.graph_id)
            self._publish(
                workflow_event(
                    "workflow_finished",
                    workflow_id=graph.graph_id,
                    ids=ids,
                    workflow_name=graph.name,
                    duration_ms=(monotonic() - start) * 1000.0,
                )
            )

        return WorkflowResult(graph)

    def _publish(self, event: Any) -> None:
        if self._bus is None:
            return
        self._bus.publish(event.topic, event.to_dict())
