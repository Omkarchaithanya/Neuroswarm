"""Agent candidate assignment — selection only, never scheduling."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from neuroswarm_arm.runtime.swarm.task_graph.graph import TaskGraph
from neuroswarm_arm.runtime.swarm.task_graph.node import TaskNode

from .events import EventBus, NodeAssigned
from .exceptions import AssignmentError
from .interfaces import IAgentCatalogPort, IArmoraBudgetPort
from .metrics import OrchestratorMetrics
from .models import AgentAssignment, BudgetSlice


class AgentAssigner:
    """Choose candidate agents for a node. HAOE owns actual scheduling."""

    def __init__(
        self,
        *,
        catalog: IAgentCatalogPort | None = None,
        budget: IArmoraBudgetPort | None = None,
        events: EventBus | None = None,
        metrics: OrchestratorMetrics | None = None,
    ) -> None:
        self.catalog = catalog
        self.budget = budget
        self.events = events
        self.metrics = metrics

    def assign(
        self,
        node: TaskNode,
        *,
        agent_pool: Sequence[str] | None = None,
        context: Mapping[str, Any] | None = None,
        workflow_id: str = "",
        execution_id: str = "",
        preferred_agent_id: str | None = None,
    ) -> AgentAssignment:
        budget_slice = self._budget_slice()
        ctx = dict(context or {})

        if preferred_agent_id:
            assignment = AgentAssignment(
                node_id=node.id,
                agent_id=preferred_agent_id,
                agent_type=node.agent_type or "",
                score=1.0,
                candidates=[preferred_agent_id],
                budget=budget_slice,
                capabilities=list(node.required_tools),
                reason="preferred_agent",
                metadata={"context_keys": sorted(ctx.keys())},
            )
            self._emit(assignment, workflow_id, execution_id)
            return assignment

        if self.catalog is not None:
            request = {
                "task": node.name or node.id,
                "task_tags": list(node.tags),
                "required_tools": list(node.required_tools),
                "required_models": list(node.required_models),
                "budget": {
                    "max_cost_usd": budget_slice.max_cost_usd,
                    "max_latency_ms": budget_slice.max_latency_ms,
                    "max_tokens": budget_slice.max_tokens,
                },
                "limit": 5,
                "metadata": {"node_id": node.id, "agent_type": node.agent_type},
            }
            result = self.catalog.select_for_task(request)
            agents = getattr(result, "agents", None)
            if agents is None and isinstance(result, Mapping):
                agents = result.get("agents", [])
            agents = list(agents or [])
            if not agents:
                raise AssignmentError(
                    f"no candidate agents for node {node.id}",
                    node_id=node.id,
                )
            top = agents[0]
            agent_id = getattr(top, "agent_id", None) or (
                top.get("agent_id") if isinstance(top, Mapping) else str(top)
            )
            score = float(getattr(top, "score", 0.0) if not isinstance(top, Mapping) else top.get("score", 0.0))
            candidates = [
                getattr(a, "agent_id", None)
                or (a.get("agent_id") if isinstance(a, Mapping) else str(a))
                for a in agents
            ]
            assignment = AgentAssignment(
                node_id=node.id,
                agent_id=str(agent_id),
                agent_type=node.agent_type or "",
                score=score,
                candidates=[str(c) for c in candidates if c],
                budget=budget_slice,
                capabilities=list(node.required_tools),
                reason="catalog_selection",
                metadata={"context_keys": sorted(ctx.keys())},
            )
            self._emit(assignment, workflow_id, execution_id)
            return assignment

        # Fallback: pick from explicit pool
        pool = list(agent_pool or [])
        if node.agent_type:
            typed = [a for a in pool if a == node.agent_type or a.endswith(node.agent_type)]
            if typed:
                pool = typed
        if not pool:
            raise AssignmentError(
                f"no agents available for node {node.id}",
                node_id=node.id,
            )
        agent_id = pool[0]
        assignment = AgentAssignment(
            node_id=node.id,
            agent_id=agent_id,
            agent_type=node.agent_type or "",
            score=1.0,
            candidates=pool[:5],
            budget=budget_slice,
            capabilities=list(node.required_tools),
            reason="agent_pool",
            metadata={"context_keys": sorted(ctx.keys())},
        )
        self._emit(assignment, workflow_id, execution_id)
        return assignment

    def assign_graph_nodes(
        self,
        graph: TaskGraph,
        node_ids: Sequence[str],
        *,
        agent_pool: Sequence[str] | None = None,
        context: Mapping[str, Any] | None = None,
        workflow_id: str = "",
        execution_id: str = "",
    ) -> dict[str, AgentAssignment]:
        out: dict[str, AgentAssignment] = {}
        for nid in node_ids:
            node = graph.nodes[nid]
            out[nid] = self.assign(
                node,
                agent_pool=agent_pool,
                context=context,
                workflow_id=workflow_id,
                execution_id=execution_id,
            )
        return out

    def _budget_slice(self) -> BudgetSlice:
        if self.budget is None:
            return BudgetSlice()
        remaining = dict(self.budget.remaining())
        return BudgetSlice(
            max_cost_usd=remaining.get("cost"),
            max_latency_ms=remaining.get("latency"),
            max_tokens=remaining.get("tokens"),
            remaining=remaining,
            metadata={"envelope_id": self.budget.envelope_id(), "frozen": self.budget.is_frozen()},
        )

    def _emit(self, assignment: AgentAssignment, workflow_id: str, execution_id: str) -> None:
        if self.metrics is not None:
            self.metrics.record_assignment()
        if self.events is not None and workflow_id and execution_id:
            self.events.emit(
                NodeAssigned(
                    workflow_id,
                    execution_id,
                    assignment.node_id,
                    agent_id=assignment.agent_id,
                    score=assignment.score,
                )
            )
