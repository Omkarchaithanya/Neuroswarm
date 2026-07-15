"""Serialize routed tools for DIPA prompt injection."""

from __future__ import annotations

import json
from typing import Any

from .models import RoutingResult, ScoredTool
from .tool_schema_builder import build_tool_schema, estimate_schema_tokens


def serialize_tools_for_prompt(tools: list[ScoredTool]) -> str:
    schemas = [t.schema or build_tool_schema(t.tool) for t in tools]
    return (
        "Available tools (semantic top-k only). Prefer these tools when applicable:\n"
        + json.dumps(schemas, indent=2)
    )


def serialize_routing_result(result: RoutingResult) -> dict[str, Any]:
    return result.to_dict()


def schemas_from_result(result: RoutingResult) -> list[dict[str, Any]]:
    out = []
    for scored in result.tools:
        schema = scored.schema or build_tool_schema(scored.tool)
        out.append(schema)
    return out


def token_stats_for_registry(all_tools: list[Any], selected: list[ScoredTool]) -> tuple[int, int]:
    before = 0
    for tool in all_tools:
        schema = build_tool_schema(tool) if hasattr(tool, "id") else tool
        before += estimate_schema_tokens(schema if isinstance(schema, dict) else build_tool_schema(tool))
    after = sum(estimate_schema_tokens(t.schema or build_tool_schema(t.tool)) for t in selected)
    return before, after
