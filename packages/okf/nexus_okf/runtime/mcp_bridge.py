from __future__ import annotations

from typing import Any

from nexus_okf.runtime.query import OKFContext


class MCPDocBridge:
    """Load OKF tool docs only after Semantic MCP Router selects tools."""

    def __init__(self, runtime: Any):
        self.runtime = runtime

    def load_after_route(self, tool_ids: list[str], budget: int = 800) -> OKFContext:
        if not tool_ids:
            return OKFContext()
        return self.runtime.load_tool_docs(tool_ids, budget=budget)
