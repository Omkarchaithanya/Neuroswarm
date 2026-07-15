"""Conversation / context filter."""

from __future__ import annotations

from .models import RouteContext, ToolRecord
from .similarity import keyword_overlap


class ContextFilter:
    def apply(
        self,
        tools: list[ToolRecord],
        context: RouteContext | None = None,
        *,
        min_overlap: float = 0.0,
    ) -> list[ToolRecord]:
        ctx = context or RouteContext()
        text = " ".join(
            [
                ctx.conversation_excerpt or "",
                ctx.task_type or "",
                " ".join(ctx.previous_tools),
                " ".join(ctx.tool_chain),
            ]
        ).strip()
        if not text or min_overlap <= 0:
            return tools
        scored = [(keyword_overlap(text, t.index_text()), t) for t in tools]
        kept = [t for score, t in scored if score >= min_overlap]
        return kept or tools
