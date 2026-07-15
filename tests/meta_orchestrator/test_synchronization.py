"""Barrier synchronization tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.meta_orchestrator import BarrierSynchronizer
from neuroswarm_arm.runtime.swarm.meta_orchestrator.events import EventBus

from .conftest import fan_graph


def test_fan_in_join() -> None:
    g = fan_graph()
    sync = BarrierSynchronizer(g)
    order = g.topological_sort()
    # last is join
    join = order[-1]
    root = order[0]
    mids = [n for n in order if n not in {root, join}]
    assert not sync.fan_in_satisfied(join, [root])
    assert sync.fan_in_satisfied(join, [root, *mids])


def test_waiting_barriers() -> None:
    g = fan_graph()
    sync = BarrierSynchronizer(g)
    order = g.topological_sort()
    join = order[-1]
    waiting = sync.waiting_barriers(completed=[order[0]], pending=[join, *order[1:]])
    assert join in waiting


def test_barrier_release_emits_event() -> None:
    g = fan_graph()
    bus = EventBus()
    sync = BarrierSynchronizer(g, events=bus)
    order = g.topological_sort()
    join = order[-1]
    mids = order[1:-1]
    assert sync.release_if_ready(
        join,
        completed=mids,
        workflow_id="wf",
        execution_id="ex",
    )
    assert any(e.type == "BarrierReleased" for e in bus.history())


def test_fan_out_ready() -> None:
    g = fan_graph()
    sync = BarrierSynchronizer(g)
    order = g.topological_sort()
    root = order[0]
    mids = order[1:-1]
    fo = sync.fan_out_ready(root, completed=[root], ready=mids)
    assert set(fo) == set(mids)
