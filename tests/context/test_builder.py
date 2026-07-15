"""Builder + basic SwarmContext construction tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.context import (
    EventBus,
    RequestContext,
    SwarmContextBuilder,
)


def test_builder_fluent():
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe(lambda e: seen.append(e.type))

    ctx = (
        SwarmContextBuilder(events=bus)
        .request(prompt="hello swarm")
        .budget(cost_usd_limit=1.0, tokens_limit=1000, frozen=True, envelope_id="env1")
        .memory(session_id="sess-1", memory_pressure=0.2)
        .execution(run_id="run-1", confidence=0.9)
        .knowledge(namespaces=["okf/domains/coding"])
        .tools(available_tools=["web_search"])
        .metrics()
        .tags("chat", "axion")
        .labels(plane="swarm")
        .build()
    )
    assert ctx.request.prompt == "hello swarm"
    assert ctx.budget.frozen is True
    assert ctx.budget.envelope_id == "env1"
    assert ctx.memory.session_id == "sess-1"
    assert "web_search" in ctx.tools.available_tools
    assert "chat" in ctx.tags
    assert ctx.labels["plane"] == "swarm"
    assert ctx.content_hash()
    assert "ContextCreated" in seen


def test_builder_with_request_object():
    ctx = SwarmContextBuilder().request(RequestContext(prompt="x")).build()
    assert ctx.request.prompt == "x"


def test_evolve_and_clone():
    ctx = SwarmContextBuilder().request(prompt="a").build()
    other = ctx.evolve(current_agent="researcher")
    assert other.current_agent == "researcher"
    assert ctx.current_agent is None
    cloned = ctx.clone()
    assert cloned.swarm_id == ctx.swarm_id
    assert cloned.content_hash() == ctx.content_hash()


def test_as_condition_map():
    ctx = (
        SwarmContextBuilder()
        .request(prompt="p")
        .budget(cost_usd_limit=5.0, cost_usd_used=1.0)
        .execution(confidence=0.8, available_tools=["t1"])
        .tools(available_tools=["t1"])
        .build()
    )
    m = ctx.as_condition_map()
    assert m["confidence"] == 0.8
    assert "budget" in m
    assert "t1" in m["available_tools"]
