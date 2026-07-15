"""Performance smoke tests (not full benchmark suite)."""

from __future__ import annotations

import time

from neuroswarm_arm.runtime.swarm.agent_registry import (
    Agent,
    AgentRegistry,
    SelectionRequest,
    build_agent_registry,
)
from neuroswarm_arm.runtime.swarm.agent_registry.capability import AgentCapability


def test_bulk_register_perf():
    reg = AgentRegistry()
    agents = [
        Agent(
            name=f"agent_{i}",
            capabilities=AgentCapability(
                supported_tasks=["t"],
                supported_backends=["llama.cpp"],
                supported_quantizations=["q4_k_m"],
            ),
            priority=i % 100,
        )
        for i in range(500)
    ]
    t0 = time.perf_counter()
    reg.bulk_register(agents)
    elapsed = time.perf_counter() - t0
    assert reg.size() == 500
    assert elapsed < 5.0


def test_selection_perf():
    svc = build_agent_registry()
    for i in range(100):
        svc.register(
            Agent(
                name=f"extra_{i}",
                agent_type="coding" if i % 2 == 0 else "research",
                capabilities=AgentCapability(
                    supported_tasks=["coding", "research"],
                    supported_tools=["nexus.tools.github"],
                    supported_backends=["llama.cpp"],
                    supported_quantizations=["q4_k_m"],
                ),
                estimated_cost=0.001 * (i % 10),
                estimated_latency=100.0 * (i % 5),
                priority=50,
            )
        )
    req = SelectionRequest(
        task="coding",
        required_tools=["nexus.tools.github"],
        limit=5,
    )
    t0 = time.perf_counter()
    for _ in range(50):
        svc.select(req)
    elapsed = time.perf_counter() - t0
    assert elapsed < 3.0


def test_lookup_indexed_fast():
    reg = AgentRegistry()
    for i in range(200):
        reg.register(
            Agent(
                name=f"idx_{i}",
                capabilities=AgentCapability(
                    supported_tools=[f"tool_{i % 10}"],
                    supported_backends=["llama.cpp"],
                    supported_quantizations=["q4_k_m"],
                ),
            )
        )
    t0 = time.perf_counter()
    for _ in range(100):
        reg.lookup_by_tool("tool_3")
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0
