"""Policy engine tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.checkpoint import (
    CheckpointPolicy,
    PolicyEngine,
    WorkflowObservation,
)

from .conftest import fresh_manager


def _obs(**kwargs) -> WorkflowObservation:
    base = dict(
        workflow_id="wf",
        execution_id="ex",
        completed_nodes=[],
        nodes_since_checkpoint=0,
        seconds_since_checkpoint=0.0,
        event_kind="tick",
    )
    base.update(kwargs)
    return WorkflowObservation(**base)


def test_always_policy() -> None:
    eng = PolicyEngine([CheckpointPolicy.always()])
    assert eng.should_checkpoint(_obs()) is True


def test_every_n_nodes() -> None:
    eng = PolicyEngine([CheckpointPolicy.every_n_nodes(3)])
    assert eng.should_checkpoint(_obs(nodes_since_checkpoint=2)) is False
    assert eng.should_checkpoint(_obs(nodes_since_checkpoint=3)) is True


def test_every_n_seconds() -> None:
    eng = PolicyEngine([CheckpointPolicy.every_n_seconds(10)])
    assert eng.should_checkpoint(_obs(seconds_since_checkpoint=9.0)) is False
    assert eng.should_checkpoint(_obs(seconds_since_checkpoint=10.0)) is True


def test_tool_and_aggregation_events() -> None:
    eng = PolicyEngine(
        [
            CheckpointPolicy.before_tool(),
            CheckpointPolicy.after_tool(),
            CheckpointPolicy.before_aggregation(),
        ]
    )
    assert eng.should_checkpoint(_obs(event_kind="before_tool"))
    assert eng.should_checkpoint(_obs(event_kind="after_tool"))
    assert eng.should_checkpoint(_obs(event_kind="before_aggregation"))
    assert eng.should_checkpoint(_obs(event_kind="tick")) is False


def test_manual_and_custom() -> None:
    eng = PolicyEngine(
        [
            CheckpointPolicy.manual(),
            CheckpointPolicy.custom(lambda o: o.tool_name == "search"),
        ]
    )
    assert eng.should_checkpoint(_obs(event_kind="manual"))
    assert eng.should_checkpoint(_obs(tool_name="search"))
    assert eng.should_checkpoint(_obs()) is False


def test_maybe_checkpoint_respects_policy() -> None:
    mgr = fresh_manager(policies=[CheckpointPolicy.every_n_nodes(2)])
    assert mgr.maybe_checkpoint(_obs(nodes_since_checkpoint=1)) is None
    cid = mgr.maybe_checkpoint(
        _obs(workflow_id="wf", execution_id="ex", nodes_since_checkpoint=2, completed_nodes=["a"])
    )
    assert cid and cid.startswith("ckpt_")
