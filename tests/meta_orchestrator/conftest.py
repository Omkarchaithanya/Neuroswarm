"""Shared fixtures / mocks for Meta Orchestrator tests."""

from __future__ import annotations

from typing import Any, Mapping

from neuroswarm_arm.runtime.swarm.task_graph import TaskGraphBuilder
from neuroswarm_arm.runtime.swarm.meta_orchestrator.models import (
    ExecutionRequest,
    ExecutionSignal,
    NodeResult,
)


class MockHaoePort:
    """In-memory HAOE execution port — succeeds every submit immediately on poll."""

    def __init__(self, *, fail_nodes: set[str] | None = None) -> None:
        self.fail_nodes = set(fail_nodes or [])
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
        if req.node_id in self.fail_nodes:
            return ExecutionSignal(
                request_id=request_id,
                execution_id=req.execution_id,
                node_id=req.node_id,
                status="failed",
                error="mock failure",
                result=NodeResult(node_id=req.node_id, success=False, error="mock failure"),
            )
        return ExecutionSignal(
            request_id=request_id,
            execution_id=req.execution_id,
            node_id=req.node_id,
            status="succeeded",
            result=NodeResult(
                node_id=req.node_id,
                success=True,
                output={"echo": req.node_id},
                metrics={"latency_ms": 1.0},
                budget_used={"cost": 0.01},
                tool_outputs={"t": "ok"},
                memory_refs=[f"mem:{req.node_id}"],
                agent_id=req.agent_id,
            ),
        )

    async def cancel(self, request_id: str, *, forced: bool = False) -> None:
        self.cancelled.append(request_id)
        self._pending.pop(request_id, None)


class MockCatalog:
    def __init__(self, agent_id: str = "agent-1") -> None:
        self.agent_id = agent_id

    def select_for_task(self, request: Mapping[str, Any]) -> Any:
        class _A:
            def __init__(self, aid: str) -> None:
                self.agent_id = aid
                self.score = 0.9

        class _R:
            def __init__(self, aid: str) -> None:
                self.agents = [_A(aid)]

        return _R(self.agent_id)

    def resolve_agent(self, agent_id: str) -> Mapping[str, Any] | None:
        return {"id": agent_id}


class MockBudget:
    def envelope_id(self) -> str:
        return "env-1"

    def remaining(self) -> Mapping[str, float | None]:
        return {"cost": 1.0, "latency": 1000.0, "tokens": 100.0}

    def is_frozen(self) -> bool:
        return True


def linear_graph():
    return (
        TaskGraphBuilder(name="linear")
        .task("a", estimated_latency=10, agent_type="worker")
        .task("b", estimated_latency=20, agent_type="worker")
        .task("c", estimated_latency=5, agent_type="worker")
        .build()
    )


def fan_graph():
    return (
        TaskGraphBuilder(name="fan")
        .task("root", estimated_latency=5)
        .parallel("a", "b")
        .aggregate("join")
        .build()
    )


def simple_context() -> dict[str, Any]:
    return {
        "swarm_id": "sw_test",
        "request_id": "req_test",
        "budget": {"cost": 1.0},
    }
