"""Propagation tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.context import (
    SwarmContextBuilder,
    branch_context,
    child_context,
    fork_context,
    subgraph_context,
)


def _base():
    return (
        SwarmContextBuilder()
        .request(prompt="propagate")
        .budget(cost_usd_limit=10.0, cost_usd_used=2.0, tokens_limit=100)
        .execution(run_id="run-parent")
        .build()
    )


def test_child_inherits_budget_and_new_span():
    parent = _base()
    child = child_context(parent, agent_id="agent-a", node_id="n1")
    assert child.swarm_id == parent.swarm_id
    assert child.budget.cost_usd_used == 2.0
    assert child.budget.cost_usd_limit == 10.0
    assert child.trace_context.trace_id == parent.trace_context.trace_id
    assert child.trace_context.span_id != parent.trace_context.span_id
    assert child.trace_context.parent_span_id == parent.trace_context.span_id
    assert child.current_agent == "agent-a"
    assert child.current_node == "n1"
    assert child.execution.depth == parent.execution.depth + 1
    assert child.metrics.propagation_count == parent.metrics.propagation_count + 1


def test_fork_new_swarm_id():
    parent = _base()
    forked = fork_context(parent, label="speculative")
    assert forked.swarm_id != parent.swarm_id
    assert forked.metadata["fork_of"] == parent.swarm_id
    assert forked.metadata["fork_label"] == "speculative"


def test_branch_and_subgraph():
    parent = _base()
    branched = branch_context(parent, branch_name="b1")
    assert branched.labels["branch"] == "b1"
    sub = subgraph_context(parent, subgraph_id="sg1", pending_nodes=["a", "b"])
    assert sub.metadata["subgraph_id"] == "sg1"
    assert sub.execution.pending_nodes == ["a", "b"]
    assert sub.execution.baggage["subgraph_id"] == "sg1"
