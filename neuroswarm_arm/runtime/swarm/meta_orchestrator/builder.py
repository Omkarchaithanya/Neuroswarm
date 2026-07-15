"""Fluent WorkflowBuilder for Meta Orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from neuroswarm_arm.runtime.swarm.task_graph.graph import TaskGraph

from .exceptions import ValidationError
from .models import WorkflowExecution

if TYPE_CHECKING:
    from .orchestrator import MetaOrchestrator


class WorkflowBuilder:
    """
    Example::

        execution = await (
            WorkflowBuilder()
            .graph(task_graph)
            .context(swarm_context)
            .agents(["agent-a", "agent-b"])
            .execute(orchestrator)
        )
    """

    def __init__(self) -> None:
        self._graph: TaskGraph | None = None
        self._context: Any = None
        self._agents: list[str] = []
        self._workflow_id: str | None = None
        self._metadata: dict[str, Any] = {}

    def graph(self, graph: TaskGraph) -> WorkflowBuilder:
        self._graph = graph
        return self

    def context(self, context: Any) -> WorkflowBuilder:
        self._context = context
        return self

    def agents(self, agents: Sequence[str]) -> WorkflowBuilder:
        self._agents = list(agents)
        return self

    def workflow_id(self, workflow_id: str) -> WorkflowBuilder:
        self._workflow_id = workflow_id
        return self

    def metadata(self, **kwargs: Any) -> WorkflowBuilder:
        self._metadata.update(kwargs)
        return self

    def build(self, orchestrator: MetaOrchestrator) -> WorkflowExecution:
        if self._graph is None:
            raise ValidationError("graph is required", field="graph")
        if self._context is None:
            raise ValidationError("context is required", field="context")
        return orchestrator.create(
            graph=self._graph,
            context=self._context,
            agents=self._agents or None,
            workflow_id=self._workflow_id,
            metadata=self._metadata or None,
        )

    async def execute(self, orchestrator: MetaOrchestrator) -> WorkflowExecution:
        execution = self.build(orchestrator)
        return await orchestrator.start(execution)
