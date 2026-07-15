"""Bidirectional adapter between swarm TaskGraph and HAOE TaskGraph."""

from __future__ import annotations

from typing import Any

from neuroswarm_arm.runtime.haoe.core.task_graph import (
    TaskEdge as HTaskEdge,
    TaskGraph as HTaskGraph,
    TaskNode as HTaskNode,
)
from neuroswarm_arm.runtime.haoe.interfaces.types import (
    CorrelationIds,
    EdgeKind as HEdgeKind,
    PriorityClass,
    ResourceEstimate,
    RetryPolicy as HRetryPolicy,
    TaskState,
)
from neuroswarm_arm.runtime.haoe.runtime.runtime_state import TaskStateMachine

from ..edge import TaskEdge
from ..enums import EdgeKind, NodeStatus, NodeType, Priority
from ..graph import TaskGraph
from ..models import RetryPolicy
from ..node import TaskNode
from ..utils import new_id


_PRIORITY_TO_HAOE = {
    Priority.CRITICAL: PriorityClass.CRITICAL,
    Priority.HIGH: PriorityClass.HIGH,
    Priority.NORMAL: PriorityClass.NORMAL,
    Priority.BACKGROUND: PriorityClass.BACKGROUND,
}

_HAOE_TO_PRIORITY = {v: k for k, v in _PRIORITY_TO_HAOE.items()}

_EDGE_TO_HAOE = {
    EdgeKind.HARD: HEdgeKind.HARD,
    EdgeKind.CONDITIONAL: HEdgeKind.CONDITIONAL,
    EdgeKind.SOFT: HEdgeKind.HARD,  # HAOE has no SOFT — map to HARD + metadata
    EdgeKind.DATA: HEdgeKind.HARD,
    EdgeKind.CONTROL: HEdgeKind.HARD,
    EdgeKind.PRIORITY: HEdgeKind.HARD,
}

_HAOE_TO_EDGE = {
    HEdgeKind.HARD: EdgeKind.HARD,
    HEdgeKind.CONDITIONAL: EdgeKind.CONDITIONAL,
    HEdgeKind.FAN_OUT: EdgeKind.HARD,
    HEdgeKind.FAN_IN: EdgeKind.HARD,
    HEdgeKind.CHECKPOINT: EdgeKind.CONTROL,
    HEdgeKind.RETRY: EdgeKind.CONTROL,
    HEdgeKind.CANCEL: EdgeKind.CONTROL,
}

_STATUS_TO_HAOE = {
    NodeStatus.PENDING: TaskState.QUEUED,
    NodeStatus.QUEUED: TaskState.QUEUED,
    NodeStatus.READY: TaskState.READY,
    NodeStatus.RUNNING: TaskState.RUNNING,
    NodeStatus.WAITING: TaskState.WAITING,
    NodeStatus.SUCCEEDED: TaskState.COMPLETED,
    NodeStatus.FAILED: TaskState.FAILED,
    NodeStatus.CANCELLED: TaskState.CANCELLED,
    NodeStatus.SKIPPED: TaskState.CANCELLED,
    NodeStatus.TIMED_OUT: TaskState.FAILED,
    NodeStatus.RETRYING: TaskState.RETRY,
    NodeStatus.CHECKPOINTED: TaskState.COMPLETED,
}

_HAOE_TO_STATUS = {
    TaskState.QUEUED: NodeStatus.QUEUED,
    TaskState.READY: NodeStatus.READY,
    TaskState.RUNNING: NodeStatus.RUNNING,
    TaskState.PAUSED: NodeStatus.WAITING,
    TaskState.WAITING: NodeStatus.WAITING,
    TaskState.RETRY: NodeStatus.RETRYING,
    TaskState.CANCELLED: NodeStatus.CANCELLED,
    TaskState.COMPLETED: NodeStatus.SUCCEEDED,
    TaskState.FAILED: NodeStatus.FAILED,
}


def to_haoe_graph(graph: TaskGraph) -> HTaskGraph:
    """Convert swarm TaskGraph → HAOE TaskGraph (preserves handler metadata)."""
    ids = CorrelationIds(
        workflow_id=str(graph.metadata.get("workflow_id", graph.graph_id)),
        request_id=str(graph.metadata.get("request_id", "")),
        trace_id=str(graph.metadata.get("trace_id", "")),
    )
    hgraph = HTaskGraph(
        graph_id=graph.graph_id,
        name=graph.name,
        ids=ids,
        context=dict(graph.metadata),
    )
    for nid, node in graph.nodes.items():
        hnode = _to_haoe_node(node)
        hgraph.nodes[hnode.node_id] = hnode
    for edge in graph.edges:
        hkind = _EDGE_TO_HAOE.get(edge.kind, HEdgeKind.HARD)
        hedge = HTaskEdge(
            src=edge.src,
            dst=edge.dst,
            kind=hkind,
            label=edge.label or edge.kind.value,
            condition=None,  # callables not portable; condition dict in metadata
        )
        # stash swarm condition for round-trip
        if edge.condition:
            # HAOE edge has no metadata field — store on dst node metadata
            dst = hgraph.nodes.get(edge.dst)
            if dst is not None:
                conds = dst.metadata.setdefault("_swarm_edge_conditions", {})
                conds[f"{edge.src}->{edge.dst}"] = edge.condition
        hgraph.edges.append(hedge)
    return hgraph


def from_haoe_graph(hgraph: HTaskGraph) -> TaskGraph:
    """Convert HAOE TaskGraph → swarm TaskGraph."""
    graph = TaskGraph(
        graph_id=hgraph.graph_id or new_id("g_"),
        name=hgraph.name,
        metadata={
            **dict(hgraph.context),
            "workflow_id": hgraph.ids.workflow_id,
            "request_id": hgraph.ids.request_id,
            "trace_id": hgraph.ids.trace_id,
            "haoe_correlation": hgraph.ids.to_dict(),
        },
    )
    for nid, hnode in hgraph.nodes.items():
        graph.nodes[nid] = _from_haoe_node(hnode)
    for hedge in hgraph.edges:
        kind = _HAOE_TO_EDGE.get(hedge.kind, EdgeKind.HARD)
        meta: dict[str, Any] = {"haoe_kind": hedge.kind.value}
        cond = None
        dst = hgraph.nodes.get(hedge.dst)
        if dst is not None:
            stored = dst.metadata.get("_swarm_edge_conditions", {})
            cond = stored.get(f"{hedge.src}->{hedge.dst}")
        if hedge.kind is HEdgeKind.CONDITIONAL and hedge.condition is not None:
            # cannot serialize callable — mark custom
            meta["has_callable_condition"] = True
        graph.edges.append(
            TaskEdge(
                src=hedge.src,
                dst=hedge.dst,
                kind=kind,
                label=hedge.label,
                condition=cond,
                metadata=meta,
            )
        )
    graph._sync_dep_links()
    return graph


def _to_haoe_node(node: TaskNode) -> HTaskNode:
    priority = _PRIORITY_TO_HAOE.get(node.priority, PriorityClass.NORMAL)
    retry = HRetryPolicy(
        max_attempts=node.retry_policy.max_attempts,
        backoff_base_s=node.retry_policy.backoff_base_s,
        backoff_factor=node.retry_policy.backoff_factor,
        backoff_max_s=node.retry_policy.backoff_max_s,
    )
    estimate = ResourceEstimate(
        memory_bytes=node.memory_requirement,
        expected_latency_ms=node.estimated_latency,
        cpu_cost=node.estimated_cost or 1.0,
    )
    meta = dict(node.metadata)
    meta["_swarm"] = {
        "agent_type": node.agent_type,
        "node_type": node.node_type.value,
        "tags": list(node.tags),
        "required_tools": list(node.required_tools),
        "required_models": list(node.required_models),
        "reasoning_budget": node.reasoning_budget,
        "condition": node.condition,
        "budget": node.budget.model_dump(mode="json"),
        "handler_key": node.handler_key,
        "display_name": node.display_name,
        "description": node.description,
        "checkpoint_id": node.checkpoint_id,
        "subgraph_ref": node.subgraph_ref,
    }
    # restore HAOE-native fields if present
    fn = meta.pop("_haoe_fn", None)
    pool = meta.pop("_haoe_pool", None)
    executor = meta.pop("_haoe_executor", None)
    affinity = meta.pop("_haoe_affinity", None)

    sm = TaskStateMachine()
    # best-effort state map — TaskStateMachine starts QUEUED
    hnode = HTaskNode(
        node_id=node.id,
        name=node.name,
        fn=fn,
        priority=priority,
        retry=retry,
        timeout_s=node.timeout,
        estimate=estimate,
        metadata=meta,
        condition_key=meta.get("condition_key"),
        is_checkpoint=node.node_type is NodeType.CHECKPOINT or bool(node.checkpoint_id),
        sm=sm,
        result=node.result,
        attempts=int(node.execution_state.get("attempts", 0)),
    )
    if pool is not None:
        hnode.pool = pool
    if executor is not None:
        hnode.executor = executor
    if affinity is not None:
        hnode.affinity = affinity
    return hnode


def _from_haoe_node(hnode: HTaskNode) -> TaskNode:
    swarm_meta = dict(hnode.metadata.get("_swarm") or {})
    meta = {k: v for k, v in hnode.metadata.items() if k != "_swarm"}
    # preserve HAOE-only fields for round-trip
    meta["_haoe_fn"] = hnode.fn
    meta["_haoe_pool"] = hnode.pool
    meta["_haoe_executor"] = hnode.executor
    meta["_haoe_affinity"] = hnode.affinity
    if hnode.condition_key:
        meta["condition_key"] = hnode.condition_key

    priority = _HAOE_TO_PRIORITY.get(hnode.priority, Priority.NORMAL)
    try:
        node_type = NodeType(swarm_meta.get("node_type", NodeType.TASK.value))
    except ValueError:
        node_type = NodeType.TASK

    retry = RetryPolicy(
        max_attempts=hnode.retry.max_attempts,
        backoff_base_s=hnode.retry.backoff_base_s,
        backoff_factor=hnode.retry.backoff_factor,
        backoff_max_s=hnode.retry.backoff_max_s,
    )
    status = _HAOE_TO_STATUS.get(hnode.state, NodeStatus.PENDING)
    return TaskNode(
        id=hnode.node_id,
        name=hnode.name,
        display_name=swarm_meta.get("display_name") or hnode.name,
        description=swarm_meta.get("description") or "",
        agent_type=swarm_meta.get("agent_type") or "",
        node_type=node_type,
        status=status,
        priority=priority,
        metadata=meta,
        tags=list(swarm_meta.get("tags") or []),
        timeout=hnode.timeout_s,
        retry_policy=retry,
        condition=swarm_meta.get("condition"),
        estimated_cost=float(hnode.estimate.cpu_cost or 0.0),
        estimated_latency=float(hnode.estimate.expected_latency_ms or 0.0),
        memory_requirement=int(hnode.estimate.memory_bytes or 0),
        required_tools=list(swarm_meta.get("required_tools") or []),
        required_models=list(swarm_meta.get("required_models") or []),
        reasoning_budget=swarm_meta.get("reasoning_budget"),
        checkpoint_id=swarm_meta.get("checkpoint_id"),
        handler_key=swarm_meta.get("handler_key") or hnode.name,
        subgraph_ref=swarm_meta.get("subgraph_ref"),
        result=hnode.result,
        error=str(hnode.error) if hnode.error else None,
        execution_state={"attempts": hnode.attempts},
    )


def map_status_to_haoe(status: NodeStatus) -> TaskState:
    return _STATUS_TO_HAOE.get(status, TaskState.QUEUED)


def map_status_from_haoe(state: TaskState) -> NodeStatus:
    return _HAOE_TO_STATUS.get(state, NodeStatus.PENDING)
