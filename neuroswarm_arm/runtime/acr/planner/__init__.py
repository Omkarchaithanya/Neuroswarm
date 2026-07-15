"""Context Planner — ContextRequirementGraph → RetrievalExecutionPlan."""

from __future__ import annotations

from neuroswarm_arm.runtime.acr.ir.plan import RetrievalExecutionPlan, RetrievalSource, RetrievalStep
from neuroswarm_arm.runtime.acr.ir.requirement import ContextRequirementGraph, RequirementKind


class ContextPlanner:
    """Budget-aware retrieval DAG planner. Plans before retrieval happens."""

    def plan(
        self,
        graph: ContextRequirementGraph,
        *,
        token_budget: int = 2000,
        latency_budget_ms: float = 200.0,
        cost_budget: float = 0.01,
        progressive: bool = True,
    ) -> RetrievalExecutionPlan:
        steps: list[RetrievalStep] = []
        # Budget split: memory 35%, knowledge 40%, tools/policy/rest 25%
        mem_budget = max(100, int(token_budget * 0.35))
        know_budget = max(100, int(token_budget * 0.40))
        rest = max(50, token_budget - mem_budget - know_budget)

        query = graph.query or graph.intent
        mem_ns: list[str] = []
        for n in graph.nodes_by_kind(RequirementKind.MEMORY):
            mem_ns.extend(n.namespaces)
        for n in graph.nodes_by_kind(RequirementKind.REFLECTION):
            steps.append(
                RetrievalStep(
                    source=RetrievalSource.REFLECTION,
                    query=query,
                    namespaces=n.namespaces or ["reflection/"],
                    limit=3,
                    priority=n.priority,
                    token_budget=min(200, rest // 2),
                    lazy=not n.must_have,
                )
            )
        steps.append(
            RetrievalStep(
                source=RetrievalSource.MEMORY,
                query=query,
                namespaces=list(dict.fromkeys(mem_ns)) or ["agents/", "users/"],
                limit=5 if any(n.must_have for n in graph.nodes_by_kind(RequirementKind.MEMORY)) else 3,
                priority=0.9,
                token_budget=mem_budget,
            )
        )
        for n in graph.nodes_by_kind(RequirementKind.REASONING):
            steps.append(
                RetrievalStep(
                    source=RetrievalSource.REASONING,
                    query=query,
                    namespaces=n.namespaces or ["reasoning/"],
                    limit=3,
                    priority=n.priority,
                    token_budget=min(150, rest // 3),
                    lazy=True,
                )
            )
        steps.append(
            RetrievalStep(
                source=RetrievalSource.OKF,
                query=query or " ".join(graph.topics[:5]) or "nexus overview",
                limit=8,
                priority=0.95,
                token_budget=know_budget,
            )
        )
        if graph.nodes_by_kind(RequirementKind.POLICY):
            steps.append(
                RetrievalStep(
                    source=RetrievalSource.POLICY,
                    query="cost budget policy",
                    limit=2,
                    priority=0.5,
                    token_budget=min(150, rest // 3),
                    lazy=True,
                )
            )
        tools = list(graph.predicted_tools)
        for n in graph.nodes_by_kind(RequirementKind.TOOL):
            tools.extend(n.metadata.get("tools") or n.entities)
        if tools:
            steps.append(
                RetrievalStep(
                    source=RetrievalSource.TOOL_DOCS,
                    query=" ".join(dict.fromkeys(tools)),
                    limit=len(dict.fromkeys(tools)),
                    priority=0.8,
                    token_budget=min(600, rest),
                    metadata={"tools": list(dict.fromkeys(tools))},
                    lazy=progressive,
                )
            )

        # Dependency: reflection before memory; memory before okf focus (soft)
        refl = [s for s in steps if s.source == RetrievalSource.REFLECTION]
        mem = [s for s in steps if s.source == RetrievalSource.MEMORY]
        okf = [s for s in steps if s.source == RetrievalSource.OKF]
        if refl and mem:
            mem[0].depends_on = [refl[0].id]
        if mem and okf:
            okf[0].depends_on = [mem[0].id]

        return RetrievalExecutionPlan(
            request_id=graph.request_id,
            steps=steps,
            token_budget=token_budget,
            latency_budget_ms=latency_budget_ms,
            cost_budget=cost_budget,
            progressive=progressive,
            metadata={"intent": graph.intent, "agent_role": graph.agent_role},
        )
