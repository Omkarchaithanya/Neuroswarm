"""Context Understanding Engine — heuristic intent → ContextRequirementGraph."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from neuroswarm_arm.runtime.acr.ir.requirement import (
    ContextRequirementGraph,
    RequirementKind,
    RequirementNode,
)

_TOOL_HINTS = {
    "github": "github-mcp",
    "git": "github-mcp",
    "search": "web-search-mcp",
    "web": "web-search-mcp",
    "code": "github-mcp",
    "arxiv": "web-search-mcp",
}

_ROLE_WORKFLOW = {
    "architect": "chat",
    "coding": "coding",
    "research": "research",
    "reviewer": "review",
    "planner": "planning",
}


class UnderstandingEngine:
    """Heuristic-first understanding (Axion-safe). Optional SLM plug-in later."""

    def understand(
        self,
        query: str,
        *,
        request_id: str = "",
        agent_role: str = "architect",
        owner: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> ContextRequirementGraph:
        q = (query or "").strip()
        rid = request_id or str(uuid4())[:16]
        role = (agent_role or "architect").lower()
        intent = self._detect_intent(q, role)
        topics = self._topics(q)
        entities = self._entities(q)
        tools = self._predict_tools(q)
        nodes: list[RequirementNode] = []

        # Always need episodic memory + institutional knowledge for chat
        nodes.append(
            RequirementNode(
                kind=RequirementKind.MEMORY,
                label="episodic_facts",
                namespaces=["agents/", "users/", "execution/"],
                priority=0.85,
                must_have=True,
                entities=entities,
            )
        )
        nodes.append(
            RequirementNode(
                kind=RequirementKind.REFLECTION,
                label="reflections",
                namespaces=["reflection/"],
                priority=0.7,
                must_have=False,
            )
        )
        nodes.append(
            RequirementNode(
                kind=RequirementKind.KNOWLEDGE,
                label="institutional_okf",
                priority=0.9,
                must_have=True,
                entities=topics,
            )
        )
        nodes.append(
            RequirementNode(
                kind=RequirementKind.POLICY,
                label="cost_policy",
                priority=0.5,
                must_have=False,
            )
        )
        if tools:
            nodes.append(
                RequirementNode(
                    kind=RequirementKind.TOOL,
                    label="tool_docs",
                    priority=0.75,
                    must_have=False,
                    entities=tools,
                    metadata={"tools": tools},
                )
            )
        if any(t in q.lower() for t in ("reason", "think", "why", "plan")):
            nodes.append(
                RequirementNode(
                    kind=RequirementKind.REASONING,
                    label="reasoning_traces",
                    namespaces=["reasoning/"],
                    priority=0.6,
                    must_have=False,
                )
            )
        for t in topics[:5]:
            nodes.append(
                RequirementNode(
                    kind=RequirementKind.TOPIC,
                    label=t,
                    priority=0.4,
                    must_have=False,
                )
            )

        edges: list[tuple[str, str]] = []
        mem = next(n for n in nodes if n.kind == RequirementKind.MEMORY)
        know = next(n for n in nodes if n.kind == RequirementKind.KNOWLEDGE)
        edges.append((mem.id, know.id))  # memory informs knowledge focus

        return ContextRequirementGraph(
            request_id=rid,
            intent=intent,
            query=q,
            agent_role=role,
            workflow_class=_ROLE_WORKFLOW.get(role, "chat"),
            topics=topics,
            entities=entities,
            predicted_tools=tools,
            nodes=nodes,
            edges=edges,
            metadata={"owner": owner, **(metadata or {})},
        )

    def _detect_intent(self, q: str, role: str) -> str:
        low = q.lower()
        if any(w in low for w in ("fix", "bug", "error", "debug")):
            return "debug"
        if any(w in low for w in ("implement", "code", "write", "refactor")):
            return "coding"
        if any(w in low for w in ("research", "paper", "survey", "compare")):
            return "research"
        if any(w in low for w in ("plan", "design", "architect")):
            return "planning"
        if any(w in low for w in ("review", "audit", "check")):
            return "review"
        return f"general_{role}"

    def _topics(self, q: str) -> list[str]:
        stop = {
            "the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "is", "are",
            "with", "how", "what", "why", "when", "please", "can", "you",
        }
        words = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}", q.lower())
        return [w for w in words if w not in stop][:12]

    def _entities(self, q: str) -> list[str]:
        # CamelCase / acronyms / quoted
        ents = re.findall(r"\b[A-Z][A-Za-z0-9_\-]{1,}\b", q)
        ents += re.findall(r'"([^"]+)"', q)
        ents += re.findall(r"`([^`]+)`", q)
        # Dedup preserve order
        seen: set[str] = set()
        out: list[str] = []
        for e in ents:
            if e.lower() not in seen:
                seen.add(e.lower())
                out.append(e)
        return out[:16]

    def _predict_tools(self, q: str) -> list[str]:
        low = q.lower()
        tools: list[str] = []
        for hint, tool in _TOOL_HINTS.items():
            if hint in low and tool not in tools:
                tools.append(tool)
        return tools
