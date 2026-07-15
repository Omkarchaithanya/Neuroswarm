"""Performance smoke tests for Meta Orchestrator."""

from __future__ import annotations

import time

from neuroswarm_arm.runtime.swarm.meta_orchestrator import ReadyNodeResolver, ResultAggregator
from neuroswarm_arm.runtime.swarm.meta_orchestrator.models import NodeResult
from neuroswarm_arm.runtime.swarm.task_graph import TaskGraphBuilder


def _wide_graph(n: int = 50):
    b = TaskGraphBuilder(name="wide").task("root", estimated_latency=1)
    # fan-out n parallel then aggregate
    names = [f"p{i}" for i in range(n)]
    b.parallel(*names)
    b.aggregate("join")
    return b.build()


def test_ready_resolve_perf() -> None:
    g = _wide_graph(40)
    resolver = ReadyNodeResolver(g)
    root = resolver.resolve()[0]
    t0 = time.perf_counter()
    for _ in range(200):
        resolver.resolve(completed=[root])
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0


def test_aggregate_perf() -> None:
    results = [
        NodeResult(
            node_id=f"n{i}",
            output={"i": i},
            metrics={"latency_ms": 1.0},
            budget_used={"cost": 0.01},
            memory_refs=[f"m{i}"],
        )
        for i in range(100)
    ]
    agg = ResultAggregator()
    t0 = time.perf_counter()
    for _ in range(50):
        agg.aggregate(results)
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0
