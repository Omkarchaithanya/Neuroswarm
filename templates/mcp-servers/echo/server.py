"""Echo MCP server — self-contained demo tools (no API keys).

Tool names match templates/mcp-servers/echo/tools/*.tool.yaml IDs.
"""
from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

mcp = FastMCP("echo")


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def echo(text: str) -> dict[str, Any]:
    """Echo the provided text back unchanged."""
    if text is None:
        raise ValueError("text is required")
    return {"text": str(text)}


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def add(a: float, b: float) -> dict[str, Any]:
    """Add two numbers and return the sum."""
    try:
        left = float(a)
        right = float(b)
    except (TypeError, ValueError) as exc:
        raise ValueError("a and b must be numbers") from exc
    return {"a": left, "b": right, "sum": left + right}


if __name__ == "__main__":
    mcp.run()
