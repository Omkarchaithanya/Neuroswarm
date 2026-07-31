"""Bridge tool response shape — TOOL_SEARCH_CONTRACT §2.3."""

from __future__ import annotations

from typing import Any


def build_bridge_response(query: str, results: list[Any], limit: int) -> dict[str, Any]:
    """Pure function: cap results to ``limit``; set truncated when input longer."""
    lim = max(1, int(limit))
    items = list(results or [])
    truncated = len(items) > lim
    capped = items[:lim]
    out: list[dict[str, Any]] = []
    for tool in capped:
        if isinstance(tool, dict):
            out.append(
                {
                    "id": str(tool.get("id") or ""),
                    "name": str(tool.get("name") or ""),
                    "description": str(tool.get("description") or ""),
                    "server": str(tool.get("server") or tool.get("namespace") or ""),
                }
            )
            continue
        server = getattr(tool, "server", None)
        if not server:
            ns = str(getattr(tool, "namespace", "") or "")
            server = ns if ns and ns != "default" else ""
            if not server:
                tid = str(getattr(tool, "id", "") or "")
                server = tid.split(".", 1)[0] if "." in tid else ""
        out.append(
            {
                "id": str(getattr(tool, "id", "") or ""),
                "name": str(getattr(tool, "name", "") or ""),
                "description": str(getattr(tool, "description", "") or ""),
                "server": str(server or ""),
            }
        )
    return {
        "mode": "tool_search",
        "query": str(query),
        "limit": lim,
        "results": out,
        "truncated": truncated,
    }
