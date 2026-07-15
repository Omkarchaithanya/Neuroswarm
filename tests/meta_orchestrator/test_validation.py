"""Validation tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.meta_orchestrator import validate_execution
from neuroswarm_arm.runtime.swarm.meta_orchestrator.exceptions import ValidationError
from neuroswarm_arm.runtime.swarm.meta_orchestrator.models import AgentAssignment, WorkflowExecution
from neuroswarm_arm.runtime.swarm.meta_orchestrator.validators import (
    assert_agents_exist,
    assert_context_exists,
    assert_graph_exists,
    assert_valid_assignment,
)

from .conftest import linear_graph, simple_context


def test_graph_required() -> None:
    with pytest.raises(ValidationError):
        assert_graph_exists(None)


def test_context_required() -> None:
    with pytest.raises(ValidationError):
        assert_context_exists(None)


def test_agents_required() -> None:
    with pytest.raises(ValidationError):
        assert_agents_exist([])


def test_invalid_assignment() -> None:
    with pytest.raises(ValidationError):
        assert_valid_assignment(AgentAssignment(node_id="", agent_id="a"))


def test_validate_execution_ok() -> None:
    g = linear_graph()
    ex = WorkflowExecution(
        graph=g,
        context=simple_context(),
        agent_pool=["a1"],
    )
    validate_execution(ex)


def test_validate_execution_no_agents() -> None:
    g = linear_graph()
    ex = WorkflowExecution(graph=g, context=simple_context())
    with pytest.raises(ValidationError):
        validate_execution(ex, allow_empty_agents=False)
