"""Performance smoke tests."""

from __future__ import annotations

import time

from neuroswarm_arm.runtime.swarm.sub_swarms import (
    LifecycleState,
    SwarmBuilder,
    SwarmSelectionRequest,
    SwarmSelector,
    SubSwarmRegistry,
)


def test_select_among_many_templates():
    registry = SubSwarmRegistry(validate_on_register=False)
    for i in range(100):
        tpl = (
            SwarmBuilder()
            .template(
                id=f"nexus.swarms.perf_{i}",
                name=f"perf_{i}",
                workflow_type="perf" if i % 2 == 0 else "other",
                category="perf",
            )
            .agents("nexus.agents.planning_agent", "nexus.agents.reviewer_agent")
            .task_graph(graph_id=f"g_{i}", snapshot={"i": i})
            .estimates(cost=0.01 * (i % 5 + 1), latency=float(1000 + i), memory=1024)
            .build()
        )
        registry.register(tpl, promote_to=LifecycleState.READY)

    selector = SwarmSelector()
    start = time.perf_counter()
    result = selector.select(
        registry.as_list(),
        SwarmSelectionRequest(workflow_type="perf", limit=10),
    )
    elapsed = time.perf_counter() - start
    assert result.templates
    assert len(result.templates) <= 10
    assert elapsed < 1.0  # soft threshold
