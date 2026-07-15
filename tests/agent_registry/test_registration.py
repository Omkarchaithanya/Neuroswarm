"""Registration / CRUD tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.agent_registry import (
    Agent,
    AgentRegistry,
    DuplicateAgentError,
    FrozenAgentError,
    LifecycleState,
    build_agent_registry,
)
from neuroswarm_arm.runtime.swarm.agent_registry.capability import AgentCapability


def _agent(name: str = "alpha", **kwargs) -> Agent:
    caps = AgentCapability(
        supported_tasks=["coding"],
        supported_tools=["nexus.tools.github"],
        supported_models=["qwen2.5-3b"],
        supported_backends=["llama.cpp"],
        supported_quantizations=["q4_k_m"],
    )
    data = {
        "name": name,
        "capabilities": caps,
        **kwargs,
    }
    return Agent.model_validate(data)


def test_register_and_get():
    reg = AgentRegistry()
    a = reg.register(_agent())
    assert a.status is LifecycleState.READY
    assert reg.get(a.id).name == "alpha"
    assert reg.size() == 1


def test_duplicate_id_rejected():
    reg = AgentRegistry()
    a = reg.register(_agent(id="agt_fixed"))
    with pytest.raises(DuplicateAgentError):
        reg.register(_agent(id="agt_fixed", name="other"))


def test_duplicate_name_rejected():
    reg = AgentRegistry()
    reg.register(_agent(name="same"))
    with pytest.raises(DuplicateAgentError):
        reg.register(_agent(name="same"))


def test_replace_and_update():
    reg = AgentRegistry()
    a = reg.register(_agent())
    b = reg.update(a.id, priority=90, description="updated")
    assert b.priority == 90
    assert b.description == "updated"
    hist = reg.history(a.id)
    assert len(hist) >= 1


def test_unregister():
    reg = AgentRegistry()
    a = reg.register(_agent())
    reg.unregister(a.id)
    assert reg.size() == 0


def test_clone():
    reg = AgentRegistry()
    a = reg.register(_agent(name="src"))
    c = reg.clone(a.id, new_name="cloned")
    assert c.id != a.id
    assert c.name == "cloned"
    assert reg.size() == 2


def test_freeze_blocks_update():
    reg = AgentRegistry()
    a = reg.register(_agent())
    reg.freeze(a.id)
    with pytest.raises(FrozenAgentError):
        reg.update(a.id, priority=10)


def test_enable_disable():
    reg = AgentRegistry()
    a = reg.register(_agent())
    d = reg.disable(a.id)
    assert d.status is LifecycleState.DISABLED
    e = reg.enable(a.id)
    assert e.status is LifecycleState.READY


def test_bulk_register():
    reg = AgentRegistry()
    n = reg.bulk_register([_agent(name=f"a{i}") for i in range(5)])
    assert n == 5
    assert reg.size() == 5


def test_build_with_builtins():
    svc = build_agent_registry(include_builtins=True)
    assert svc.registry.size() >= 10
