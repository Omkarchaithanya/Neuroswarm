"""Result aggregation tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.meta_orchestrator import ResultAggregator
from neuroswarm_arm.runtime.swarm.meta_orchestrator.events import EventBus
from neuroswarm_arm.runtime.swarm.meta_orchestrator.models import NodeResult


def test_merge_outputs_metadata_metrics() -> None:
    bus = EventBus()
    agg = ResultAggregator(events=bus)
    results = [
        NodeResult(
            node_id="a",
            output={"x": 1},
            metadata={"m": 1},
            metrics={"latency_ms": 2.0},
            budget_used={"cost": 0.1},
            tool_outputs={"search": "hit"},
            memory_refs=["r1"],
        ),
        NodeResult(
            node_id="b",
            output={"y": 2},
            metadata={"m": 2},
            metrics={"latency_ms": 3.0},
            budget_used={"cost": 0.2},
            tool_outputs={"search": "hit2"},
            memory_refs=["r1", "r2"],
        ),
    ]
    out = agg.aggregate(results, workflow_id="wf", execution_id="ex")
    assert out.outputs["a"] == {"x": 1}
    assert out.outputs["b"] == {"y": 2}
    assert out.metrics["latency_ms"] == 5.0
    assert out.budgets["cost"] == pytest.approx(0.3)
    assert "r1" in out.memory_refs and "r2" in out.memory_refs
    assert any(e.type == "AggregationFinished" for e in bus.history())


def test_merge_pair() -> None:
    agg = ResultAggregator()
    left = agg.aggregate([NodeResult(node_id="a", output=1, metrics={"t": 1})])
    right = agg.aggregate([NodeResult(node_id="b", output=2, metrics={"t": 2})])
    merged = agg.merge_pair(left, right)
    assert set(merged.node_ids) == {"a", "b"}
    assert merged.metrics["t"] == 3.0
