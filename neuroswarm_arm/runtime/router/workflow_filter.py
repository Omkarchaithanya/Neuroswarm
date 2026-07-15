"""Workflow-stage filter."""

from __future__ import annotations

from .models import RouteContext, ToolRecord


class WorkflowFilter:
    def apply(self, tools: list[ToolRecord], context: RouteContext | None = None) -> list[ToolRecord]:
        ctx = context or RouteContext()
        if not ctx.workflow_stage:
            return tools
        preferred = [t for t in tools if not t.workflow_stages or ctx.workflow_stage in t.workflow_stages]
        return preferred or tools
