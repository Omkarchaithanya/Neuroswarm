"""Workflow identity helpers and graph/context binding."""

from __future__ import annotations

from typing import Any, Sequence

from neuroswarm_arm.runtime.swarm.task_graph.graph import TaskGraph

from ._utils import new_id, utc_now
from .models import WorkflowExecution
from .workflow_state import WorkflowStatus


def bind_workflow(
    *,
    graph: TaskGraph,
    context: Any,
    agents: Sequence[str] | None = None,
    workflow_id: str | None = None,
    execution_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> WorkflowExecution:
    """Create a Created WorkflowExecution bound to graph + context."""
    node_ids = sorted(graph.nodes.keys())
    ctx_id = None
    if context is not None:
        ctx_id = getattr(context, "swarm_id", None) or getattr(context, "request_id", None)

    return WorkflowExecution(
        workflow_id=workflow_id or new_id("wf_"),
        execution_id=execution_id or new_id("ex_"),
        graph=graph,
        graph_id=getattr(graph, "graph_id", "") or "",
        context=context,
        context_id=str(ctx_id) if ctx_id else None,
        pending_nodes=node_ids,
        ready_nodes=[],
        current_nodes=[],
        completed_nodes=[],
        failed_nodes=[],
        skipped_nodes=[],
        agent_pool=list(agents or []),
        status=WorkflowStatus.CREATED,
        created_at=utc_now(),
        updated_at=utc_now(),
        metadata=dict(metadata or {}),
    )


class Workflow:
    """Thin wrapper around WorkflowExecution for identity ops."""

    def __init__(self, execution: WorkflowExecution) -> None:
        self.execution = execution

    @property
    def workflow_id(self) -> str:
        return self.execution.workflow_id

    @property
    def execution_id(self) -> str:
        return self.execution.execution_id

    @property
    def status(self) -> WorkflowStatus:
        return self.execution.status

    def graph(self) -> TaskGraph:
        return self.execution.graph
