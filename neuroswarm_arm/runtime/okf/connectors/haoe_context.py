from __future__ import annotations

from typing import Any

from nexus_okf.runtime.mem0_bridge import merge_mem0_okf
from nexus_okf.server.app import create_okf_router


def build_haoe_context_handler(okf_runtime: Any, memory: Any | None = None):
    """Return callable for HAOE mem0_recall / okf_context / okf_tool_docs nodes."""

    state: dict[str, Any] = {"facts": [], "knowledge": None, "tool_docs": None, "merged": ""}

    def mem0_recall(ctx: Any) -> list[str]:
        query = ""
        req = ctx.baggage.get("request")
        # request may not be in baggage; handlers close over it
        facts: list[str] = []
        if memory is not None:
            agent_id = getattr(ctx.ids, "agent_id", "") or "default"
            try:
                messages = getattr(req, "messages", None) if req else None
                if messages:
                    query = getattr(messages[-1], "content", "") or ""
                facts = list(memory.search(agent_id, query or "context", limit=5) or [])
            except Exception:
                facts = []
        state["facts"] = facts
        ctx.baggage["mem0_facts"] = facts
        return facts

    def okf_context(ctx: Any, request: Any = None, query_text: str = "") -> str:
        req = request
        query = query_text
        if not query and req is not None:
            messages = getattr(req, "messages", None) or []
            if messages:
                query = getattr(messages[-1], "content", "") or ""
        profile = "architect"
        if req is not None:
            profile = getattr(req, "agent_role", None) or profile
            # map common roles
            role = str(profile).lower()
            if "research" in role:
                profile = "research"
            elif "code" in role or "tool" in role:
                profile = "coding"
            elif "review" in role:
                profile = "reviewer"
            elif "plan" in role:
                profile = "planner"
        knowledge = okf_runtime.query(query or "nexus overview", agent_profile=profile)
        state["knowledge"] = knowledge
        ctx.baggage["okf_tokens"] = int(getattr(knowledge, "tokens_used", 0) or 0)
        ctx.baggage["okf_knowledge"] = getattr(knowledge, "text", "") or ""
        return getattr(knowledge, "text", "") or ""

    def okf_tool_docs(ctx: Any) -> str:
        tool_names = list(ctx.baggage.get("tool_names") or [])
        docs = okf_runtime.load_tool_docs(tool_names, budget=600)
        state["tool_docs"] = docs
        ctx.baggage["okf_tool_docs"] = getattr(docs, "text", "") or ""
        merged = merge_mem0_okf(state.get("facts") or [], state.get("knowledge"), docs)
        state["merged"] = merged
        ctx.baggage["okf_merged_context"] = merged
        return merged

    return {
        "mem0_recall": mem0_recall,
        "okf_context": okf_context,
        "okf_tool_docs": okf_tool_docs,
        "state": state,
    }


__all__ = ["build_haoe_context_handler", "create_okf_router", "merge_mem0_okf"]
