"""Serialize routed tools for DIPA prompt injection."""

from __future__ import annotations

import json
from typing import Any

from .models import RoutingResult, ScoredTool
from .tool_schema_builder import build_tool_schema, estimate_schema_tokens


def _lean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Drop bulky fields first when fitting a token budget."""
    lean = dict(schema)
    lean.pop("output_schema", None)
    lean.pop("examples", None)
    lean.pop("example_prompts", None)
    fn = lean.get("function")
    if isinstance(fn, dict):
        fn2 = dict(fn)
        fn2.pop("examples", None)
        lean["function"] = fn2
    return lean


def _payload_tokens(header: str, schemas: list[dict[str, Any]]) -> int:
    return estimate_schema_tokens({"header": header, "tools": schemas})


def serialize_tools_for_prompt(
    tools: list[ScoredTool],
    *,
    max_tokens: int | None = None,
) -> str:
    schemas = [t.schema or build_tool_schema(t.tool) for t in tools]
    header = "Available tools (semantic top-k only). Prefer these tools when applicable:\n"
    if max_tokens is None or max_tokens <= 0:
        return header + json.dumps(schemas, indent=2)

    budget = int(max_tokens)
    # Pass 1: drop output_schema / examples.
    working = [_lean_schema(s) for s in schemas]
    if _payload_tokens(header, working) <= budget:
        return header + json.dumps(working, indent=2)

    # Pass 2: drop lowest-ranked tools until under budget.
    while len(working) > 1 and _payload_tokens(header, working) > budget:
        working.pop()
    if _payload_tokens(header, working) <= budget:
        return header + json.dumps(working, indent=2)

    # Pass 3: names only.
    names = [
        {"name": (s.get("function") or {}).get("name") or s.get("id")}
        for s in working
    ]
    return header + json.dumps(names, indent=2)


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
