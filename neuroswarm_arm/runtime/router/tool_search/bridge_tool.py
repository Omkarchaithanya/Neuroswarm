"""Frozen Hermes tool_search bridge schema — TOOL_SEARCH_CONTRACT §2.3."""

from __future__ import annotations

from typing import Any

BRIDGE_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "tool_search",
        "description": (
            "Search the deferred tool catalog by free-text query. Returns "
            "name+description listings grouped by server. Use this when the "
            "user's request may match a tool you don't see in the active tools list."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text tool/feature query",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                    "description": "Max results; capped at max_search_limit.",
                },
                "scope": {
                    "type": "string",
                    "enum": ["all", "server"],
                    "default": "all",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}
