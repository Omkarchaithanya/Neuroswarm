"""Shared fixtures for Sub Swarm tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.sub_swarms import (
    LifecycleState,
    SwarmBuilder,
    SwarmSelectionRequest,
    SubSwarmManager,
    SubSwarmRegistry,
    build_sub_swarm_manager,
)


@pytest.fixture
def empty_registry() -> SubSwarmRegistry:
    return SubSwarmRegistry(validate_on_register=True)


@pytest.fixture
def manager() -> SubSwarmManager:
    return build_sub_swarm_manager(register_builtins=True, promote_builtins_to_ready=True)


@pytest.fixture
def sample_template():
    return (
        SwarmBuilder()
        .template(
            id="nexus.swarms.test_sample",
            name="test_sample",
            workflow_type="testing",
            category="test",
        )
        .agents("nexus.agents.planning_agent", "nexus.agents.reviewer_agent")
        .context("request", "budget")
        .budget("envelope_id")
        .tools("nexus.tools.web_search")
        .models("qwen2.5-3b")
        .backends("cascade")
        .task_graph(graph_id="g_test", graph_name="test", snapshot={"nodes": {}})
        .estimates(cost=0.01, latency=1000.0, memory=1024, cpu=2.0, tokens=500.0)
        .tags("test", "sample")
        .build()
    )


@pytest.fixture
def selection_request() -> SwarmSelectionRequest:
    return SwarmSelectionRequest(
        workflow_type="coding",
        limit=5,
    )
