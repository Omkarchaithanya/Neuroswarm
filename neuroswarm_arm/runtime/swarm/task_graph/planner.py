"""Workflow planner templates → TaskGraph (no handler execution)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .builders import TaskGraphBuilder
from .enums import EdgeKind, NodeType, Priority
from .graph import TaskGraph
from .node import TaskNode
from .utils import new_id


class WorkflowPlanner:
    """Pure graph construction templates consumed later by HAOE."""

    def plan_chat(
        self,
        *,
        name: str = "chat",
        include_mem0: bool = True,
        include_okf: bool = True,
        metadata: Mapping[str, Any] | None = None,
    ) -> TaskGraph:
        """Linear chat DAG matching HAOE plan_chat shape."""
        b = TaskGraphBuilder(name=name, **dict(metadata or {}))
        steps: list[str] = []
        if include_mem0:
            steps.append("mem0_recall")
        if include_okf:
            steps.append("okf_context")
        steps.extend(
            [
                "semantic_route",
                "okf_tool_docs",
                "kv_session",
                "cascade",
                "kv_checkpoint",
                "response",
            ]
        )
        prev: str | None = None
        for step in steps:
            ntype = NodeType.CHECKPOINT if "checkpoint" in step else NodeType.TASK
            if step == "cascade":
                ntype = NodeType.INFERENCE
            elif step == "semantic_route":
                ntype = NodeType.ROUTING
            elif step.startswith("mem0") or step.startswith("okf") or step.startswith("kv"):
                ntype = NodeType.MEMORY
            kwargs: dict[str, Any] = {
                "node_type": ntype,
                "handler_key": step,
                "depends_on": [prev] if prev else [],
            }
            if step == "kv_checkpoint":
                kwargs["checkpoint_id"] = "kv"
            b.task(step, **kwargs)
            # last node id
            prev = b._last[0]
        return b.build(validate=True)

    def plan_multi_agent(
        self,
        *,
        name: str = "multi_agent",
        parallel_agents: Sequence[str] = ("research", "planning", "memory"),
        metadata: Mapping[str, Any] | None = None,
    ) -> TaskGraph:
        """
        planner → (research ∥ planning ∥ memory) → aggregator → reason → review → stream
        """
        b = (
            TaskGraphBuilder(name=name, **dict(metadata or {}))
            .task("planner", node_type=NodeType.AGENT, priority=Priority.HIGH)
            .parallel(*parallel_agents, agent_type="worker")
            .aggregate("aggregate")
            .task("reason", node_type=NodeType.AGENT)
            .task("review", node_type=NodeType.AGENT)
            .task("stream", node_type=NodeType.TASK, handler_key="stream")
        )
        return b.build(validate=True)

    def plan_single(
        self,
        name: str,
        *,
        handler_key: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> TaskGraph:
        g = TaskGraph(name=name, metadata=dict(metadata or {}))
        node = TaskNode(
            id=new_id("n_"),
            name=name,
            display_name=name,
            handler_key=handler_key or name,
            node_type=NodeType.TASK,
        )
        g.add_node(node)
        return g.freeze()

    def plan_from_steps(
        self,
        steps: Sequence[str],
        *,
        name: str = "custom",
        parallel_groups: Mapping[str, Sequence[str]] | None = None,
    ) -> TaskGraph:
        """Build linear graph; ``parallel_groups`` maps barrier_name → sibling step names."""
        b = TaskGraphBuilder(name=name)
        parallel_groups = dict(parallel_groups or {})
        emitted: set[str] = set()
        for step in steps:
            if step in emitted:
                continue
            group = None
            for gname, members in parallel_groups.items():
                if step in members:
                    group = (gname, list(members))
                    break
            if group:
                _, members = group
                b.parallel(*members)
                emitted.update(members)
            else:
                b.task(step)
                emitted.add(step)
        return b.build(validate=True)
