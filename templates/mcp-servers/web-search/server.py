"""Web Search MCP server — REAL implementation (FastMCP + Brave Search API).

Replaces the fake stub that only echoed its own tool description back.
Auth: export BRAVE_API_KEY=BSA... (https://brave.com/search/api/).

Run: python server.py          (stdio, for local MCP clients)
Test: npx @modelcontextprotocol/inspector python server.py
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from fastmcp import FastMCP

BRAVE_API = "https://api.search.brave.com/res/v1/web/search"
API_KEY = os.environ.get("BRAVE_API_KEY")

mcp = FastMCP("web-search")


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search the web via Brave Search API.

    Args:
        query: search query string
        limit: max results (1-20)
    """
    if not API_KEY:
        raise ValueError(
            "BRAVE_API_KEY is not set. Create a key at https://brave.com/search/api/ and export it."
        )
    if not query or not query.strip():
        raise ValueError("query is required")
    limit = max(1, min(int(limit), 20))
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": API_KEY,
    }
    params = {"q": query.strip(), "count": limit}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(BRAVE_API, headers=headers, params=params)
        if resp.status_code == 401:
            raise ValueError("Brave Search auth failed. Check BRAVE_API_KEY is valid.")
        if resp.status_code == 403:
            raise ValueError(
                "Brave Search forbidden (403). Check plan entitlements for the web search endpoint."
            )
        if resp.status_code == 404:
            raise ValueError("Brave Search endpoint not found. Check API base URL / plan.")
        if resp.status_code == 429:
            raise ValueError("Brave Search rate limit hit. Back off and retry; check quota.")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ValueError(f"Brave Search HTTP {resp.status_code}: {resp.text[:200]}") from None
        data = resp.json()
    results = (data.get("web") or {}).get("results") or []
    return [
        {
            "title": item.get("title"),
            "url": item.get("url"),
            "description": item.get("description"),
        }
        for item in results[:limit]
    ]


if __name__ == "__main__":
    mcp.run()
