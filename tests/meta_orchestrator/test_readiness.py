"""Ready node discovery tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.meta_orchestrator import ReadyNodeResolver
from neuroswarm_arm.runtime.swarm.task_graph import Never, TaskGraphBuilder

from .conftest import fan_graph, linear_graph


def test_ready_roots_when_nothing_completed() -> None:
    g = linear_graph()
    ready = ReadyNodeResolver(g).resolve()
    roots = [n for n, node in g.nodes.items() if not node.dependencies and True]
    # first node in linear builder chain is only ready
    assert len(ready) == 1
    assert ready[0] in g.nodes


def test_ready_advances_after_completion() -> None:
    g = linear_graph()
    resolver = ReadyNodeResolver(g)
    first = resolver.resolve()[0]
    order = g.topological_sort()
    assert first == order[0]
    ready2 = resolver.resolve(completed=[order[0]])
    assert ready2 == [order[1]]


def test_fan_out_parallel_ready() -> None:
    g = fan_graph()
    resolver = ReadyNodeResolver(g)
    root = resolver.resolve()[0]
    ready = resolver.resolve(completed=[root])
    assert len(ready) == 2


def test_cancel_requested_yields_empty() -> None:
    g = linear_graph()
    assert ReadyNodeResolver(g).resolve(cancel_requested=True) == []


def test_running_excluded() -> None:
    g = linear_graph()
    resolver = ReadyNodeResolver(g)
    first = resolver.resolve()[0]
    assert resolver.resolve(running=[first]) == []


def test_node_condition_never_skipped_via_should_skip() -> None:
    g = (
        TaskGraphBuilder(name="cond")
        .task("a")
        .condition(Never().to_dict())
        .task("b")
        .build()
    )
    resolver = ReadyNodeResolver(g)
    order = g.topological_sort()
    assert resolver.should_skip(order[1], completed=[order[0]])


def test_incremental_ready() -> None:
    g = fan_graph()
    resolver = ReadyNodeResolver(g)
    root = resolver.resolve()[0]
    prev = resolver.resolve(completed=[root])
    incr = resolver.incremental(prev, completed=[root])
    assert incr == []
