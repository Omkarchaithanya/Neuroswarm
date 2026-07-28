"""Web Search MCP server — FastMCP + SerpAPI (+ optional URL fetch).

Auth: export SERPAPI_API_KEY=...
  (alias: SERP_API_KEY)
Tool names match templates/mcp-servers/web-search/tools/*.tool.yaml IDs.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from fastmcp import FastMCP

SERPAPI_BASE = "https://serpapi.com/search.json"
API_KEY = (os.environ.get("SERPAPI_API_KEY") or os.environ.get("SERP_API_KEY") or "").strip()

mcp = FastMCP("web-search")


def _require_key() -> None:
    if not API_KEY:
        raise ValueError(
            "SERPAPI_API_KEY is not set. Create a key at https://serpapi.com/ and export it "
            "(alias env: SERP_API_KEY)."
        )


async def _serpapi_get(params: dict[str, Any]) -> dict[str, Any]:
    _require_key()
    query = dict(params)
    query["api_key"] = API_KEY
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(SERPAPI_BASE, params=query)
        if resp.status_code == 401:
            raise ValueError("SerpAPI auth failed. Check SERPAPI_API_KEY is valid.")
        if resp.status_code == 403:
            raise ValueError("SerpAPI forbidden (403). Check plan entitlements for this engine.")
        if resp.status_code == 429:
            raise ValueError("SerpAPI rate limit hit. Back off and retry; check quota.")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            raise ValueError(f"SerpAPI HTTP {resp.status_code}: {resp.text[:200]}") from None
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            raise ValueError(f"SerpAPI error: {data.get('error')}")
        return data


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search the web via SerpAPI (Google engine)."""
    if not query or not query.strip():
        raise ValueError("query is required")
    limit = max(1, min(int(limit), 20))
    data = await _serpapi_get(
        {
            "engine": "google",
            "q": query.strip(),
            "num": limit,
        }
    )
    results = data.get("organic_results") or []
    return [
        {
            "title": item.get("title"),
            "url": item.get("link"),
            "description": item.get("snippet"),
            "position": item.get("position"),
        }
        for item in results[:limit]
    ]


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def news(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search news via SerpAPI Google News."""
    if not query or not query.strip():
        raise ValueError("query is required")
    limit = max(1, min(int(limit), 20))
    try:
        data = await _serpapi_get(
            {
                "engine": "google_news",
                "q": query.strip(),
                "num": limit,
            }
        )
        results = data.get("news_results") or data.get("organic_results") or []
        return [
            {
                "title": item.get("title"),
                "url": item.get("link"),
                "description": item.get("snippet") or item.get("source"),
                "date": item.get("date"),
            }
            for item in results[:limit]
        ]
    except ValueError as exc:
        # Fallback to web search with news intent if news engine unavailable
        if "403" in str(exc) or "forbidden" in str(exc).lower() or "engine" in str(exc).lower():
            return await search(query=f"{query} news", limit=limit)
        raise


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def images(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search images via SerpAPI Google Images."""
    if not query or not query.strip():
        raise ValueError("query is required")
    limit = max(1, min(int(limit), 20))
    try:
        data = await _serpapi_get(
            {
                "engine": "google_images",
                "q": query.strip(),
                "num": limit,
            }
        )
        results = data.get("images_results") or []
        return [
            {
                "title": item.get("title"),
                "url": item.get("original") or item.get("link"),
                "thumbnail": item.get("thumbnail"),
                "source": item.get("source"),
            }
            for item in results[:limit]
        ]
    except ValueError as exc:
        if "403" in str(exc) or "forbidden" in str(exc).lower():
            return await search(query=f"{query} images", limit=limit)
        raise


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def scholar(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search scholarly results via SerpAPI Google Scholar."""
    if not query or not query.strip():
        raise ValueError("query is required")
    limit = max(1, min(int(limit), 20))
    try:
        data = await _serpapi_get(
            {
                "engine": "google_scholar",
                "q": query.strip(),
                "num": limit,
            }
        )
        results = data.get("organic_results") or []
        return [
            {
                "title": item.get("title"),
                "url": item.get("link"),
                "description": item.get("snippet"),
                "cited_by": (item.get("inline_links") or {}).get("cited_by", {}).get("total")
                if isinstance(item.get("inline_links"), dict)
                else None,
            }
            for item in results[:limit]
        ]
    except ValueError as exc:
        if "403" in str(exc) or "forbidden" in str(exc).lower():
            return await search(
                query=f"{query.strip()} site:scholar.google.com OR filetype:pdf",
                limit=limit,
            )
        raise


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def fetch_url(url: str, max_bytes: int = 100_000) -> dict[str, Any]:
    """Fetch a URL and return truncated text/body (SSRF-safe)."""
    import sys
    from pathlib import Path

    _repo = Path(__file__).resolve().parents[3]
    if str(_repo) not in sys.path:
        sys.path.insert(0, str(_repo))
    from neuroswarm_arm.runtime.router.mcp_ssrf import SsrfError, fetch_url_ssrf_safe

    max_bytes = max(1024, min(int(max_bytes), 500_000))
    tenant_id = (os.environ.get("NSA_MCP_TENANT_ID") or "").strip() or None
    try:
        return await fetch_url_ssrf_safe(
            url, max_bytes=max_bytes, max_redirects=5, tenant_id=tenant_id
        )
    except SsrfError as exc:
        raise ValueError(str(exc)) from None


if __name__ == "__main__":
    mcp.run()
