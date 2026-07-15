"""Context propagation: parent / child / fork / branch / subgraph."""

from __future__ import annotations

from typing import Any

from ._utils import new_id
from .budget import BudgetContext
from .context import SwarmContext
from .events import ContextUpdated, EventBus
from .exceptions import PropagationError
from .metrics import ContextMetrics


def child_context(
    parent: SwarmContext,
    *,
    agent_id: str | None = None,
    node_id: str | None = None,
    events: EventBus | None = None,
) -> SwarmContext:
    """DAG fan-out child: inherits budget used+limits, new execution/trace spans."""
    tracing = parent.trace_context.child(agent_id=agent_id)
    execution = parent.execution.child()
    if node_id:
        execution = execution.model_copy(update={"current_node": node_id})
    if agent_id:
        execution = execution.model_copy(update={"current_agent": agent_id})
    budget = parent.budget.propagate()
    metrics = parent.metrics.bump("propagation_count")
    child = parent.model_copy(
        deep=True,
        update={
            "execution_id": tracing.execution_id,
            "trace_context": tracing,
            "execution": execution,
            "budget": budget,
            "metrics": metrics,
            "current_node": node_id or parent.current_node,
            "current_agent": agent_id or parent.current_agent,
            "snapshot_id": None,
        },
    ).touch()
    if events is not None:
        events.emit(
            ContextUpdated(
                child.swarm_id,
                kind="child",
                parent_execution_id=parent.execution_id,
                execution_id=child.execution_id,
            )
        )
    return child


def fork_context(
    parent: SwarmContext,
    *,
    label: str = "",
    events: EventBus | None = None,
) -> SwarmContext:
    """Independent fork with new swarm_id (branch for speculative paths)."""
    forked = parent.clone()
    forked = forked.evolve(
        swarm_id=new_id("sw_"),
        execution_id=new_id("ex_"),
        execution=parent.execution.child(),
        trace_context=parent.trace_context.child(),
        metrics=parent.metrics.bump("propagation_count"),
        metadata={**parent.metadata, "fork_of": parent.swarm_id, "fork_label": label},
        snapshot_id=None,
    )
    if events is not None:
        events.emit(
            ContextUpdated(
                forked.swarm_id,
                kind="fork",
                parent_swarm_id=parent.swarm_id,
                label=label,
            )
        )
    return forked


def branch_context(
    parent: SwarmContext,
    *,
    branch_name: str,
    events: EventBus | None = None,
) -> SwarmContext:
    """Named branch sharing swarm_id but new execution lineage."""
    if not branch_name:
        raise PropagationError("branch_name required")
    branched = child_context(parent, events=events)
    return branched.evolve(
        labels={**branched.labels, "branch": branch_name},
        metadata={**branched.metadata, "branch": branch_name},
    )


def subgraph_context(
    parent: SwarmContext,
    *,
    subgraph_id: str,
    pending_nodes: list[str] | None = None,
    events: EventBus | None = None,
) -> SwarmContext:
    """Context scoped to a Task Graph subgraph."""
    if not subgraph_id:
        raise PropagationError("subgraph_id required")
    sub = child_context(parent, events=events)
    execution = sub.execution.model_copy(
        update={
            "pending_nodes": list(pending_nodes or []),
            "completed_nodes": [],
            "baggage": {**sub.execution.baggage, "subgraph_id": subgraph_id},
        }
    )
    task_graph = sub.task_graph.model_copy(
        update={"metadata": {**sub.task_graph.metadata, "subgraph_id": subgraph_id}}
    )
    return sub.evolve(
        execution=execution,
        task_graph=task_graph,
        metadata={**sub.metadata, "subgraph_id": subgraph_id},
    )


def propagate_budget(parent_budget: BudgetContext) -> BudgetContext:
    return parent_budget.propagate()


def bump_propagation_metrics(metrics: ContextMetrics) -> ContextMetrics:
    return metrics.bump("propagation_count")
