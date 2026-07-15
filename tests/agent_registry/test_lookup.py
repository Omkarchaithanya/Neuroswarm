"""Lookup / discovery tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.agent_registry import (
    Agent,
    AgentRegistry,
    build_agent_registry,
)
from neuroswarm_arm.runtime.swarm.agent_registry.capability import AgentCapability
from neuroswarm_arm.runtime.swarm.agent_registry.discovery import AgentDiscovery


def _make(name: str, **kwargs) -> Agent:
    caps = kwargs.pop(
        "capabilities",
        AgentCapability(
            supported_tasks=["coding"],
            supported_tools=["nexus.tools.github"],
            supported_models=["qwen2.5-3b"],
            supported_backends=["llama.cpp"],
            supported_quantizations=["q4_k_m"],
            supports_planning=True,
        ),
    )
    return Agent(name=name, capabilities=caps, tags=["coding", "dev"], **kwargs)


def test_lookup_by_name_tool_model_backend():
    reg = AgentRegistry()
    a = reg.register(_make("coder"))
    assert reg.get_by_name("coder").id == a.id
    assert a.id in {x.id for x in reg.lookup_by_tool("nexus.tools.github")}
    assert a.id in {x.id for x in reg.lookup_by_model("qwen2.5-3b")}
    assert a.id in {x.id for x in reg.lookup_by_backend("llama.cpp")}
    assert a.id in {x.id for x in reg.lookup_by_quantization("q4_k_m")}


def test_lookup_by_tags_and_capability():
    reg = AgentRegistry()
    a = reg.register(_make("coder"))
    tagged = reg.lookup_by_tags(["coding"])
    assert any(x.id == a.id for x in tagged)
    caps = reg.lookup_by_capability("flag:planning")
    assert any(x.id == a.id for x in caps)


def test_lookup_by_cost_latency_priority_health():
    reg = AgentRegistry()
    a = reg.register(
        _make("cheap", estimated_cost=0.01, estimated_latency=100.0, priority=77)
    )
    assert a.id in {x.id for x in reg.lookup_by_cost(0.05)}
    assert a.id in {x.id for x in reg.lookup_by_latency(200.0)}
    assert a.id in {x.id for x in reg.lookup_by_priority(77)}
    assert a.id in {x.id for x in reg.lookup_by_health("healthy")}


def test_predicate_query():
    reg = AgentRegistry()
    reg.register(_make("a", priority=10))
    reg.register(_make("b", priority=90))
    high = reg.query(lambda ag: ag.priority >= 50)
    assert len(high) == 1 and high[0].name == "b"


def test_discovery_helpers():
    svc = build_agent_registry()
    disc = AgentDiscovery(svc.registry.as_list)
    assert disc.by_task("coding")
    assert disc.selectable()
    assert disc.supporting_tool("nexus.tools.github")
