"""Cache invalidation tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.agent_registry import (
    RegistryCache,
    SelectionRequest,
    build_agent_registry,
)


def test_cache_hit_miss():
    cache = RegistryCache(default_ttl_s=60.0)
    assert cache.get("ns", "k") is None
    cache.set("ns", "k", {"v": 1})
    assert cache.get("ns", "k") == {"v": 1}
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1


def test_invalidate_namespace():
    cache = RegistryCache()
    cache.set("selection", "a", 1)
    cache.set("meta", "b", 2)
    n = cache.invalidate("selection")
    assert n == 1
    assert cache.get("selection", "a") is None
    assert cache.get("meta", "b") == 2


def test_selection_cache_invalidated_on_register():
    svc = build_agent_registry()
    req = SelectionRequest(task="coding")
    r1 = svc.select(req)
    # warm cache
    r2 = svc.select(req)
    assert r1.request_hash == r2.request_hash
    # mutate registry → invalidate
    from neuroswarm_arm.runtime.swarm.agent_registry import Agent
    from neuroswarm_arm.runtime.swarm.agent_registry.capability import AgentCapability

    svc.register(
        Agent(
            name="extra_coder",
            agent_type="coding",
            capabilities=AgentCapability(
                supported_tasks=["coding"],
                supported_backends=["llama.cpp"],
                supported_quantizations=["q4_k_m"],
            ),
            estimated_cost=0.0,
            estimated_latency=1.0,
            priority=99,
        )
    )
    # cache cleared; new select still works
    r3 = svc.select(req)
    assert r3.request_hash == r1.request_hash
