"""Serialization tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.meta_orchestrator import dumps, loads, WorkflowStatus
from neuroswarm_arm.runtime.swarm.meta_orchestrator.models import WorkflowExecution
from neuroswarm_arm.runtime.swarm.task_graph.graph import TaskGraph

from .conftest import linear_graph, simple_context


def test_roundtrip() -> None:
    g = linear_graph()
    ex = WorkflowExecution(
        graph=g,
        context=simple_context(),
        agent_pool=["a1"],
        status=WorkflowStatus.READY,
        completed_nodes=[],
    )
    raw = dumps(ex)
    restored = loads(raw)
    assert restored.workflow_id == ex.workflow_id
    assert restored.execution_id == ex.execution_id
    assert restored.status == WorkflowStatus.READY
    assert isinstance(restored.graph, TaskGraph)
    assert restored.graph.graph_id == g.graph_id
    assert restored.context["swarm_id"] == "sw_test"
