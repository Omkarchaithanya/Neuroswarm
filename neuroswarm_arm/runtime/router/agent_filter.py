"""Agent-role filter."""

from __future__ import annotations

from .models import RouteContext, ToolRecord


class AgentFilter:
    def apply(self, tools: list[ToolRecord], context: RouteContext | None = None) -> list[ToolRecord]:
        ctx = context or RouteContext()
        if not ctx.agent_role:
            return tools
        preferred = [t for t in tools if not t.agent_roles or ctx.agent_role in t.agent_roles]
        return preferred or tools
