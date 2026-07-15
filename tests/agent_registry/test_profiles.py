"""Built-in profile tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.agent_registry import (
    BUILTIN_PROFILE_FACTORIES,
    all_builtin_profiles,
    build_agent_registry,
    register_builtin_profiles,
)
from neuroswarm_arm.runtime.swarm.agent_registry.registry import AgentRegistry


def test_ten_builtin_factories():
    assert len(BUILTIN_PROFILE_FACTORIES) == 10
    profiles = all_builtin_profiles()
    assert len(profiles) == 10
    ids = {p.id for p in profiles}
    assert "nexus.agents.coding_agent" in ids
    assert "nexus.agents.research_analyst" in ids


def test_register_builtin_profiles():
    reg = AgentRegistry()
    n = register_builtin_profiles(reg)
    assert n == 10
    assert reg.size() == 10


def test_service_interfaces_smoke():
    svc = build_agent_registry()
    coding = svc.resolve_agent_type("coding")
    assert coding is not None
    assert svc.has_capability(coding.id, "task:coding") or "coding" in coding.effective_tasks()
    assert svc.estimated_cost(coding.id) >= 0
    assert svc.preferred_models(coding.id)
    assert svc.agent_priority(coding.id) > 0
    assert "agents/" in svc.memory_namespace(coding.id)
    assert svc.list_ready_agents()
    assert svc.metrics_snapshot()
    bound = svc.bind_node("n1", "coding")
    assert bound == coding.id
