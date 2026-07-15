"""Dispatch ExecutionRequest payloads to HAOE via port."""

from __future__ import annotations

from typing import Any, Mapping

from .interfaces import IDipaHintsPort, IHaoeExecutionPort
from .models import AgentAssignment, ExecutionRequest, WorkflowExecution


class Dispatcher:
    """Build and submit HAOE execution requests. Never schedules workers."""

    def __init__(
        self,
        haoe: IHaoeExecutionPort,
        *,
        dipa_hints: IDipaHintsPort | None = None,
    ) -> None:
        self.haoe = haoe
        self.dipa_hints = dipa_hints
        self._inflight: dict[str, ExecutionRequest] = {}

    async def dispatch(
        self,
        execution: WorkflowExecution,
        assignment: AgentAssignment,
        *,
        context_payload: Mapping[str, Any] | None = None,
        priority: int = 2,
    ) -> ExecutionRequest:
        payload = dict(context_payload or {})
        if self.dipa_hints is not None and execution.context is not None:
            baggage = self.dipa_hints.inference_baggage(execution.context)
            payload = {**payload, **dict(baggage)}

        request = ExecutionRequest(
            execution_id=execution.execution_id,
            workflow_id=execution.workflow_id,
            node_id=assignment.node_id,
            agent_id=assignment.agent_id,
            agent_type=assignment.agent_type,
            context_ref=execution.context_id,
            context_payload=payload,
            budget=assignment.budget,
            correlation=dict(execution.correlation),
            graph_id=execution.graph_id,
            priority=priority,
            metadata={"assignment_reason": assignment.reason},
        )
        request_id = await self.haoe.submit(request)
        # Allow port to return/override request id
        if request_id and request_id != request.request_id:
            request.request_id = request_id
        self._inflight[request.request_id] = request
        return request

    async def cancel(self, request_id: str, *, forced: bool = False) -> None:
        await self.haoe.cancel(request_id, forced=forced)
        self._inflight.pop(request_id, None)

    def inflight(self) -> dict[str, ExecutionRequest]:
        return dict(self._inflight)

    def drop(self, request_id: str) -> None:
        self._inflight.pop(request_id, None)
