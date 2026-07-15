"""Build MCP-compatible tool schemas for prompt injection."""

from __future__ import annotations

from typing import Any

from .models import ToolRecord


def build_tool_schema(tool: ToolRecord) -> dict[str, Any]:
    parameters = tool.input_schema or {
        "type": "object",
        "properties": {
            key: {"type": "string", "description": str(desc)} for key, desc in tool.params.items()
        },
    }
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": parameters,
        },
        "id": tool.id,
        "namespace": tool.namespace,
        "version": tool.version,
        "category": tool.category,
        "cost_usd": tool.cost_usd,
        "p50_latency_ms": tool.p50_latency_ms,
        "capabilities": tool.capabilities,
        "tags": tool.tags,
        "output_schema": tool.output_schema,
    }


def estimate_schema_tokens(schema: dict[str, Any]) -> int:
    # Rough 4 chars/token heuristic for reduction metrics
    import json

    return max(1, len(json.dumps(schema, separators=(",", ":"))) // 4)
