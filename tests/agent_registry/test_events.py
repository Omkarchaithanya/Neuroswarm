"""Event bus tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.agent_registry import (
    Agent,
    AgentRegistry,
    EventBus,
    SelectionRequest,
    build_agent_registry,
)
from neuroswarm_arm.runtime.swarm.agent_registry.capability import AgentCapability
from neuroswarm_arm.runtime.swarm.agent_registry.events import RegistryEvent


def test_register_emits_events():
    bus = EventBus()
    seen: list[RegistryEvent] = []
    bus.subscribe(seen.append)
    reg = AgentRegistry(events=bus)
    reg.register(
        Agent(
            name="e1",
            capabilities=AgentCapability(
                supported_backends=["llama.cpp"],
                supported_quantizations=["q4_k_m"],
            ),
        )
    )
    types = [e.type for e in seen]
    assert "AgentRegistered" in types
    assert seen[0].to_otel_attributes()["nexus.agent_registry.event"] == "AgentRegistered"


def test_disable_enable_events():
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(lambda e: seen.append(e.type))
    reg = AgentRegistry(events=bus)
    a = reg.register(
        Agent(
            name="e2",
            capabilities=AgentCapability(
                supported_backends=["mock"],
                supported_quantizations=["none"],
            ),
        )
    )
    reg.disable(a.id)
    reg.enable(a.id)
    assert "AgentDisabled" in seen
    assert "AgentEnabled" in seen


def test_selection_event():
    svc = build_agent_registry()
    seen: list[str] = []
    svc.events.subscribe(lambda e: seen.append(e.type))
    svc.select(SelectionRequest(task="routing"))
    assert "SelectionPerformed" in seen
