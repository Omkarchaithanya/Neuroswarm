"""Validation helpers for Meta Orchestrator workflows."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .exceptions import ValidationError
from .models import AgentAssignment, WorkflowExecution
from .workflow_state import WORKFLOW_TRANSITIONS, WorkflowStatus


def assert_graph_exists(graph: Any) -> None:
    if graph is None:
        raise ValidationError("graph is required", field="graph")
    nodes = getattr(graph, "nodes", None)
    if nodes is None and isinstance(graph, dict):
        nodes = graph.get("nodes")
    if not nodes:
        raise ValidationError("graph has no nodes", field="graph")


def assert_context_exists(context: Any) -> None:
    if context is None:
        raise ValidationError("context is required", field="context")


def assert_agents_exist(agents: Sequence[str] | None) -> None:
    if agents is None:
        raise ValidationError("agents list is required", field="agents")
    if len(agents) == 0:
        raise ValidationError("agents list must be non-empty", field="agents")


def assert_no_orphan_nodes(graph: Any) -> list[str]:
    """Return orphan node ids (disconnected when graph has >1 node)."""
    nodes = getattr(graph, "nodes", None)
    edges = getattr(graph, "edges", None)
    if nodes is None and isinstance(graph, dict):
        nodes = graph.get("nodes", {})
        edges = graph.get("edges", [])
    if not isinstance(nodes, dict) or len(nodes) <= 1:
        return []
    touched: set[str] = set()
    edge_iter: Iterable[Any]
    if edges is None:
        edge_iter = []
    else:
        edge_iter = edges
    for edge in edge_iter:
        if hasattr(edge, "src"):
            touched.add(edge.src)
            touched.add(edge.dst)
        elif isinstance(edge, Mapping):
            touched.add(str(edge["src"]))
            touched.add(str(edge["dst"]))
    orphans = sorted(set(nodes.keys()) - touched)
    return orphans


def assert_valid_assignment(assignment: AgentAssignment) -> None:
    if not assignment.node_id:
        raise ValidationError("assignment.node_id required", field="assignment.node_id")
    if not assignment.agent_id:
        raise ValidationError("assignment.agent_id required", field="assignment.agent_id")


def assert_valid_workflow_state(status: WorkflowStatus, target: WorkflowStatus) -> None:
    allowed = WORKFLOW_TRANSITIONS.get(status, frozenset())
    if target not in allowed:
        raise ValidationError(
            f"invalid workflow state transition: {status} -> {target}",
            field="status",
        )


def validate_execution(execution: WorkflowExecution, *, allow_empty_agents: bool = False) -> None:
    assert_graph_exists(execution.graph)
    assert_context_exists(execution.context)
    if not allow_empty_agents and not execution.agent_pool and not execution.assigned_agents:
        raise ValidationError("no agents available for workflow", field="agents")
    orphans = assert_no_orphan_nodes(execution.graph)
    if orphans and len(execution.node_set()) > 1:
        # Soft warning path: raise only when every node is orphan (fully disconnected)
        if len(orphans) == len(execution.node_set()):
            raise ValidationError(
                f"all nodes are orphans: {orphans}",
                field="graph",
            )
    for assignment in execution.assigned_agents.values():
        assert_valid_assignment(assignment)
        if assignment.node_id not in execution.node_set() and execution.node_set():
            raise ValidationError(
                f"assignment for unknown node: {assignment.node_id}",
                field="assigned_agents",
            )
