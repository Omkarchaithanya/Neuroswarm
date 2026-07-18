"""HAOE execution port adapters for Meta Orchestrator composition root."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.meta_orchestrator.models import (
    ExecutionRequest,
    ExecutionSignal,
    NodeResult,
)


class InstantHaoeAdapter:
    """Deterministic HAOE port — succeeds each node on first poll.

    Used for durable long-horizon workflow resume demos when node handlers
    are not yet bound to live HAOE worker pools. Scheduling still goes through
    Meta Orchestrator → IHaoeExecutionPort.
    """

    def __init__(self) -> None:
        self.submitted: list[ExecutionRequest] = []
        self._pending: dict[str, ExecutionRequest] = {}
        self.cancelled: list[str] = []

    async def submit(self, request: ExecutionRequest) -> str:
        self.submitted.append(request)
        self._pending[request.request_id] = request
        return request.request_id

    async def poll(self, request_id: str) -> ExecutionSignal | None:
        req = self._pending.pop(request_id, None)
        if req is None:
            return None
        return ExecutionSignal(
            request_id=request_id,
            execution_id=req.execution_id,
            node_id=req.node_id,
            status="succeeded",
            result=NodeResult(
                node_id=req.node_id,
                success=True,
                output={"echo": req.node_id, "handler": req.metadata.get("handler_key")},
                metrics={"latency_ms": 1.0},
                agent_id=req.agent_id,
            ),
        )

    async def cancel(self, request_id: str, *, forced: bool = False) -> None:
        self.cancelled.append(request_id)
        self._pending.pop(request_id, None)


class StaticAgentCatalog:
    """Minimal catalog so assignment succeeds without Agent Registry wiring."""

    def __init__(self, agent_id: str = "workflow-agent") -> None:
        self.agent_id = agent_id

    def select_for_task(self, request: dict) -> object:
        class _A:
            def __init__(self, aid: str) -> None:
                self.agent_id = aid
                self.score = 1.0

        class _R:
            def __init__(self, aid: str) -> None:
                self.agents = [_A(aid)]

        return _R(self.agent_id)

    def resolve_agent(self, agent_id: str) -> dict | None:
        return {"id": agent_id}
