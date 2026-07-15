"""Tool-level hard filters."""

from __future__ import annotations

from .models import RouteContext, ToolRecord


class ToolFilter:
    def apply(self, tools: list[ToolRecord], context: RouteContext | None = None) -> list[ToolRecord]:
        ctx = context or RouteContext()
        out = []
        for tool in tools:
            if ctx.required_permissions:
                if not set(ctx.required_permissions).issubset(set(tool.permissions or []) | {"*"}):
                    # Allow tools with empty permissions only when policy empty or wildcard
                    if tool.permissions and "*" not in tool.permissions:
                        if not set(ctx.required_permissions).issubset(set(tool.permissions)):
                            continue
            if ctx.security_policies:
                blocked = {p.lower() for p in ctx.security_policies if p.startswith("deny:")}
                if any(f"deny:{tool.id}" == b or f"deny:{tool.namespace}" == b for b in blocked):
                    continue
            if tool.failure_rate >= 0.95 and tool.reliability < 0.1:
                continue
            out.append(tool)
        return out
