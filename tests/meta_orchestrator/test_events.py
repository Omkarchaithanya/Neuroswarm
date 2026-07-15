"""Event emission tests."""

from __future__ import annotations

import asyncio

from neuroswarm_arm.runtime.swarm.meta_orchestrator import (
    EventBus,
    WorkflowBuilder,
    build_meta_orchestrator,
)

from .conftest import MockHaoePort, linear_graph, simple_context


def test_workflow_events() -> None:
    bus = EventBus()
    haoe = MockHaoePort()
    orch = build_meta_orchestrator(haoe=haoe, events=bus)

    async def _run():
        return await (
            WorkflowBuilder()
            .graph(linear_graph())
            .context(simple_context())
            .agents(["agent-1"])
            .execute(orch)
        )

    asyncio.run(_run())
    types = [e.type for e in bus.history()]
    assert "WorkflowCreated" in types
    assert "WorkflowStarted" in types
    assert "NodeAssigned" in types
    assert "NodeCompleted" in types
    assert "WorkflowCompleted" in types
    ev = bus.history()[0]
    attrs = ev.to_otel_attributes()
    assert attrs["nexus.meta_orchestrator.event"] == ev.type
