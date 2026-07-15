from __future__ import annotations

from typing import Any


def load_tool_docs_after_route(okf_runtime: Any, tool_ids: list[str], budget: int = 800) -> Any:
    return okf_runtime.load_tool_docs(tool_ids, budget=budget)
