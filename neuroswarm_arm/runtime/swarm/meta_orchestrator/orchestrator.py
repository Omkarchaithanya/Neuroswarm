"""MetaOrchestrator facade — workflow coordination entrypoint."""

from __future__ import annotations

from typing import Any, Sequence

from neuroswarm_arm.runtime.swarm.task_graph.graph import TaskGraph

from .assignment import AgentAssigner
from .checkpoint import CheckpointCoordinator
from .coordinator import Coordinator
from .events import EventBus, WorkflowCancelled, WorkflowCreated, WorkflowStarted
from .exceptions import WorkflowNotFoundError
from .interfaces import (
    IAgentCatalogPort,
    IArmoraBudgetPort,
    ICheckpointManagerPort,
    IDipaHintsPort,
    IExperienceStorePort,
    IHaoeExecutionPort,
    IMetaOrchestratorPort,
    ISwarmContextPort,
)
from .lifecycle import WorkflowLifecycle
from .metrics import OrchestratorMetrics
from .models import WorkflowExecution
from .validators import validate_execution
from .workflow import bind_workflow
from .workflow_state import WorkflowStatus


class MetaOrchestrator:
    """Production workflow coordinator.

    Implements IMetaOrchestratorPort (attach/detach context).
    Never owns scheduling, planning, inference, or memory.
    """

    def __init__(
        self,
        *,
        haoe: IHaoeExecutionPort,
        catalog: IAgentCatalogPort | None = None,
        budget: IArmoraBudgetPort | None = None,
        context_port: ISwarmContextPort | None = None,
        dipa_hints: IDipaHintsPort | None = None,
        checkpoint_manager: ICheckpointManagerPort | None = None,
        experience_store: IExperienceStorePort | None = None,
        events: EventBus | None = None,
        metrics: OrchestratorMetrics | None = None,
        max_parallel: int | None = None,
        fail_fast: bool = False,
        validate: bool = True,
    ) -> None:
        self.events = events or EventBus()
        self.metrics = metrics or OrchestratorMetrics()
        self.lifecycle = WorkflowLifecycle()
        self.context_port = context_port
        self.validate = validate
        self._contexts: dict[str, Any] = {}
        self._executions: dict[str, WorkflowExecution] = {}

        assigner = AgentAssigner(
            catalog=catalog,
            budget=budget,
            events=self.events,
            metrics=self.metrics,
        )
        from .dispatcher import Dispatcher

        dispatcher = Dispatcher(haoe, dipa_hints=dipa_hints)
        checkpoint = CheckpointCoordinator(
            checkpoint_manager=checkpoint_manager,
            experience_store=experience_store,
            events=self.events,
            metrics=self.metrics,
            lifecycle=self.lifecycle,
        )
        self.coordinator = Coordinator(
            haoe=haoe,
            assigner=assigner,
            events=self.events,
            metrics=self.metrics,
            dispatcher=dispatcher,
            checkpoint=checkpoint,
            max_parallel=max_parallel,
            fail_fast=fail_fast,
        )

    # --- IMetaOrchestratorPort ---

    def attach_context(self, context: Any) -> None:
        ctx_id = (
            getattr(context, "swarm_id", None)
            or getattr(context, "request_id", None)
            or id(context)
        )
        key = str(ctx_id)
        self._contexts[key] = context
        if self.context_port is not None:
            self.context_port.attach(context, execution_id=key)

    def detach_context(self, context_id: str) -> None:
        self._contexts.pop(context_id, None)

    # --- Workflow API ---

    def create(
        self,
        *,
        graph: TaskGraph,
        context: Any,
        agents: Sequence[str] | None = None,
        workflow_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowExecution:
        execution = bind_workflow(
            graph=graph,
            context=context,
            agents=agents,
            workflow_id=workflow_id,
            metadata=metadata,
        )
        if self.validate:
            validate_execution(execution, allow_empty_agents=bool(agents is None))
        self.attach_context(context)
        self.events.emit(
            WorkflowCreated(execution.workflow_id, execution.execution_id, graph_id=execution.graph_id)
        )
        execution.events.append(
            self.events.history()[-1].to_dict() if self.events.history() else {}
        )
        self._executions[execution.execution_id] = execution
        return execution

    async def start(self, execution: WorkflowExecution | str) -> WorkflowExecution:
        ex = self._resolve(execution)
        if ex.status == WorkflowStatus.CREATED:
            self.lifecycle.mark_ready(ex)
        self.events.emit(WorkflowStarted(ex.workflow_id, ex.execution_id))
        ex = await self.coordinator.coordinate(ex)
        self._executions[ex.execution_id] = ex
        return ex

    async def run(
        self,
        *,
        graph: TaskGraph,
        context: Any,
        agents: Sequence[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowExecution:
        execution = self.create(graph=graph, context=context, agents=agents, metadata=metadata)
        return await self.start(execution)

    async def step(self, execution: WorkflowExecution | str) -> WorkflowExecution:
        ex = self._resolve(execution)
        if ex.status == WorkflowStatus.CREATED:
            self.lifecycle.mark_ready(ex)
            self.lifecycle.mark_running(ex)
        ex = await self.coordinator.step(ex)
        self._executions[ex.execution_id] = ex
        return ex

    def cancel(self, execution: WorkflowExecution | str, *, forced: bool = False) -> WorkflowExecution:
        ex = self._resolve(execution)
        ex.cancel_requested = True
        if forced and ex.status not in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }:
            self.lifecycle.mark_cancelled(ex)
        self.events.emit(
            WorkflowCancelled(ex.workflow_id, ex.execution_id, forced=forced)
        )
        self._executions[ex.execution_id] = ex
        return ex

    def checkpoint(self, execution: WorkflowExecution | str) -> Any:
        ex = self._resolve(execution)
        handle = self.coordinator.checkpoint.create(ex)
        self._executions[ex.execution_id] = ex
        return handle

    def restore(self, execution: WorkflowExecution | str, checkpoint_id: str) -> WorkflowExecution:
        ex = self._resolve(execution)
        restored = self.coordinator.checkpoint.restore(ex, checkpoint_id)
        self._executions[restored.execution_id] = restored
        return restored

    def get(self, execution_id: str) -> WorkflowExecution:
        return self._resolve(execution_id)

    def _resolve(self, execution: WorkflowExecution | str) -> WorkflowExecution:
        if isinstance(execution, WorkflowExecution):
            return execution
        ex = self._executions.get(execution)
        if ex is None:
            raise WorkflowNotFoundError(execution)
        return ex


def build_meta_orchestrator(
    *,
    haoe: IHaoeExecutionPort,
    catalog: IAgentCatalogPort | None = None,
    budget: IArmoraBudgetPort | None = None,
    context_port: ISwarmContextPort | None = None,
    dipa_hints: IDipaHintsPort | None = None,
    checkpoint_manager: ICheckpointManagerPort | None = None,
    experience_store: IExperienceStorePort | None = None,
    events: EventBus | None = None,
    metrics: OrchestratorMetrics | None = None,
    max_parallel: int | None = None,
    fail_fast: bool = False,
    validate: bool = True,
) -> MetaOrchestrator:
    """Factory — composition root helper."""
    return MetaOrchestrator(
        haoe=haoe,
        catalog=catalog,
        budget=budget,
        context_port=context_port,
        dipa_hints=dipa_hints,
        checkpoint_manager=checkpoint_manager,
        experience_store=experience_store,
        events=events,
        metrics=metrics,
        max_parallel=max_parallel,
        fail_fast=fail_fast,
        validate=validate,
    )


# Structural satisfaction of Protocol
_: type[IMetaOrchestratorPort] = MetaOrchestrator
