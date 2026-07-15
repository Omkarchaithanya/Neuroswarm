"""Capability model tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.agent_registry import Agent, AgentCapability
from neuroswarm_arm.runtime.swarm.agent_registry.profile import coding_agent, research_agent


def test_capability_keys():
    caps = AgentCapability(
        supported_tasks=["coding"],
        supported_tools=["t1"],
        supports_streaming=True,
        supports_planning=True,
    )
    keys = caps.capability_keys()
    assert "task:coding" in keys
    assert "tool:t1" in keys
    assert "flag:streaming" in keys
    assert "flag:planning" in keys


def test_overlaps():
    caps = AgentCapability(supported_tools=["a", "b", "c"])
    assert caps.overlaps(["a", "b"], attr="supported_tools") == 1.0
    assert caps.overlaps(["a", "x"], attr="supported_tools") == 0.5
    assert caps.overlaps([], attr="supported_tools") == 1.0


def test_agent_denorm_from_capability():
    a = coding_agent()
    assert a.supported_tools
    assert a.supported_models
    assert a.streaming_support is True


def test_builtin_realistic_capabilities():
    r = research_agent()
    assert "research" in r.capabilities.supported_tasks
    assert r.capabilities.supports_reasoning is True
    assert r.capabilities.max_context >= 8192
