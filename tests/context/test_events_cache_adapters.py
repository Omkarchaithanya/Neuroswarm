"""Events + cache + adapter tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.context import (
    ContextCache,
    EventBus,
    SwarmContextBuilder,
)
from neuroswarm_arm.runtime.swarm.context.adapters import (
    from_task_graph_context,
    to_task_graph_context,
)


def test_event_bus():
    bus = EventBus()
    seen = []
    bus.subscribe(lambda e: seen.append(e.type))
    ctx = SwarmContextBuilder(events=bus).request(prompt="ev").build()
    assert ctx.swarm_id
    assert seen == ["ContextCreated"]
    assert bus.history()


def test_cache_hit_miss():
    cache = ContextCache(default_ttl_s=30, max_entries=8)
    assert cache.get(ContextCache.NS_SNAPSHOT, "a") is None
    cache.set(ContextCache.NS_SNAPSHOT, "a", {"ok": True})
    assert cache.get(ContextCache.NS_SNAPSHOT, "a") == {"ok": True}
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert cache.invalidate(ContextCache.NS_SNAPSHOT) == 1


def test_task_graph_adapter_roundtrip():
    ctx = (
        SwarmContextBuilder()
        .request(prompt="legacy")
        .budget(cost_usd_limit=2.0, cost_usd_used=0.5, envelope_id="e", frozen=True)
        .memory(session_id="sess", memory_pressure=0.1)
        .execution(run_id="run", confidence=0.7, available_tools=["t"])
        .tools(available_tools=["t"])
        .tracing(agent_id="ag1")
        .build()
    )
    legacy = to_task_graph_context(ctx)
    assert legacy.swarm_id == ctx.swarm_id
    assert legacy.budget.cost_usd_limit == 2.0
    assert legacy.budget.frozen is True
    assert legacy.memory.session_id == "sess"
    assert "t" in legacy.execution.available_tools
    back = from_task_graph_context(legacy)
    assert back.swarm_id == ctx.swarm_id
    assert back.budget.cost_usd_used == 0.5
    assert back.memory.session_id == "sess"
    assert back.execution.confidence == 0.7
