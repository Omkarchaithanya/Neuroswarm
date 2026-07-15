"""Agent assignment tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.meta_orchestrator import AgentAssigner
from neuroswarm_arm.runtime.swarm.meta_orchestrator.exceptions import AssignmentError
from neuroswarm_arm.runtime.swarm.meta_orchestrator.events import EventBus

from .conftest import MockBudget, MockCatalog, linear_graph


def test_assign_from_pool() -> None:
    g = linear_graph()
    node = next(iter(g.nodes.values()))
    assigner = AgentAssigner()
    a = assigner.assign(node, agent_pool=["agent-x", "agent-y"])
    assert a.agent_id == "agent-x"
    assert a.node_id == node.id
    assert "agent-y" in a.candidates


def test_assign_from_catalog() -> None:
    g = linear_graph()
    node = next(iter(g.nodes.values()))
    bus = EventBus()
    assigner = AgentAssigner(catalog=MockCatalog("cat-1"), budget=MockBudget(), events=bus)
    a = assigner.assign(
        node,
        workflow_id="wf",
        execution_id="ex",
        context={"k": 1},
    )
    assert a.agent_id == "cat-1"
    assert a.budget.metadata.get("envelope_id") == "env-1"
    assert any(e.type == "NodeAssigned" for e in bus.history())


def test_preferred_agent() -> None:
    g = linear_graph()
    node = next(iter(g.nodes.values()))
    a = AgentAssigner().assign(node, preferred_agent_id="pref")
    assert a.agent_id == "pref"
    assert a.reason == "preferred_agent"


def test_assign_empty_raises() -> None:
    g = linear_graph()
    node = next(iter(g.nodes.values()))
    with pytest.raises(AssignmentError):
        AgentAssigner().assign(node, agent_pool=[])
