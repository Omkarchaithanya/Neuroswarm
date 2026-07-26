"""Web Search MCP server — FastMCP + Brave Search API (+ optional URL fetch).

Auth: export BRAVE_API_KEY=BSA...
Tool names match templates/mcp-servers/web-search/tools/*.tool.yaml IDs.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from fastmcp import FastMCP

BRAVE_WEB = "https://api.search.brave.com/res/v1/web/search"
BRAVE_NEWS = "https://api.search.brave.com/res/v1/news/search"
BRAVE_IMAGES = "https://api.search.brave.com/res/v1/images/search"
API_KEY = os.environ.get("BRAVE_API_KEY")

mcp = FastMCP("web-search")


def _require_key() -> None:
    if not API_KEY:
        raise ValueError(
            "BRAVE_API_KEY is not set. Create a key at https://brave.com/search/api/ and export it."
        )


async def _brave_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    _require_key()
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": API_KEY or "",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code == 401:
            raise ValueError("Brave Search auth failed. Check BRAVE_API_KEY is valid.")
        if resp.status_code == 403:
            raise ValueError(
                "Brave Search forbidden (403). Check plan entitlements for this endpoint."
            )
        if resp.status_code == 404:
            raise ValueError("Brave Search endpoint not found. Check API base URL / plan.")
        if resp.status_code == 429:
            raise ValueError("Brave Search rate limit hit. Back off and retry; check quota.")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            raise ValueError(f"Brave Search HTTP {resp.status_code}: {resp.text[:200]}") from None
        return resp.json()


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search the web via Brave Search API."""
    if not query or not query.strip():
        raise ValueError("query is required")
    limit = max(1, min(int(limit), 20))
    data = await _brave_get(BRAVE_WEB, {"q": query.strip(), "count": limit})
    results = (data.get("web") or {}).get("results") or []
    return [
        {
            "title": item.get("title"),
            "url": item.get("url"),
            "description": item.get("description"),
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
    """Search news via Brave (falls back to web search if news endpoint unavailable)."""
    if not query or not query.strip():
        raise ValueError("query is required")
    limit = max(1, min(int(limit), 20))
    try:
        data = await _brave_get(BRAVE_NEWS, {"q": query.strip(), "count": limit})
        results = (data.get("results") or data.get("news") or {}).get("results") if isinstance(
            data.get("news"), dict
        ) else data.get("results")
        if results is None:
            results = ((data.get("news") or {}) if isinstance(data.get("news"), dict) else {}).get(
                "results"
            ) or []
        if not results and isinstance(data.get("results"), list):
            results = data["results"]
        return [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "description": item.get("description") or item.get("age"),
            }
            for item in (results or [])[:limit]
        ]
    except ValueError as exc:
        if "404" in str(exc) or "forbidden" in str(exc).lower():
            # Plan may not include news — fall back to web with news intent.
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
    """Search images via Brave (falls back to web search if images endpoint unavailable)."""
    if not query or not query.strip():
        raise ValueError("query is required")
    limit = max(1, min(int(limit), 20))
    try:
        data = await _brave_get(BRAVE_IMAGES, {"q": query.strip(), "count": limit})
        results = data.get("results") or []
        return [
            {
                "title": item.get("title"),
                "url": item.get("url") or item.get("properties", {}).get("url"),
                "thumbnail": item.get("thumbnail", {}).get("src")
                if isinstance(item.get("thumbnail"), dict)
                else item.get("thumbnail"),
            }
            for item in results[:limit]
        ]
    except ValueError as exc:
        if "404" in str(exc) or "forbidden" in str(exc).lower():
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
    """Academic-oriented web search (Brave web with scholar-biased query)."""
    if not query or not query.strip():
        raise ValueError("query is required")
    return await search(query=f"{query.strip()} site:scholar.google.com OR filetype:pdf", limit=limit)


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
