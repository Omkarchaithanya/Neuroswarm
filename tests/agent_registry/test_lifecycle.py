"""Lifecycle transition tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.agent_registry import (
    AgentRegistry,
    LifecycleError,
    LifecycleState,
)
from neuroswarm_arm.runtime.swarm.agent_registry.agent import Agent
from neuroswarm_arm.runtime.swarm.agent_registry.capability import AgentCapability
from neuroswarm_arm.runtime.swarm.agent_registry.lifecycle import can_transition, transition


def test_can_transition_matrix():
    assert can_transition(LifecycleState.READY, LifecycleState.BUSY)
    assert can_transition(LifecycleState.FAILED, LifecycleState.RESTARTING)
    assert not can_transition(LifecycleState.RETIRED, LifecycleState.READY)


def test_transition_raises():
    with pytest.raises(LifecycleError):
        transition("x", LifecycleState.RETIRED, LifecycleState.READY)


def test_registry_set_lifecycle():
    reg = AgentRegistry()
    a = reg.register(
        Agent(
            name="life",
            capabilities=AgentCapability(
                supported_backends=["mock"],
                supported_quantizations=["none"],
            ),
        )
    )
    busy = reg.set_lifecycle(a.id, LifecycleState.BUSY)
    assert busy.status is LifecycleState.BUSY
    ready = reg.set_lifecycle(a.id, LifecycleState.READY)
    assert ready.status is LifecycleState.READY
