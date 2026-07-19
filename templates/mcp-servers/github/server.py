"""GitHub MCP server — REAL implementation (FastMCP + GitHub REST API v3).

Replaces the fake stub that only echoed its own tool description back.
Auth: export GITHUB_TOKEN=ghp_xxx (repo scope minimum for private repos;
public repos work unauthenticated but at 60 req/hr instead of 5000 req/hr).

Run: python server.py          (stdio, for local MCP clients)
Test: npx @modelcontextprotocol/inspector python server.py
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from fastmcp import FastMCP

GITHUB_API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN")

mcp = FastMCP("github")


def _headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


async def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{GITHUB_API}{path}", headers=_headers(), params=params or {})
        if resp.status_code == 404:
            raise ValueError(
                f"Not found: {path}. Check the repo/owner spelling and that it's accessible with the current token."
            )
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            raise ValueError(
                "GitHub rate limit hit. Set GITHUB_TOKEN to raise the limit from 60/hr to 5000/hr."
            )
        if resp.status_code == 403:
            raise ValueError(
                f"Forbidden: {path}. Check GITHUB_TOKEN scopes and that you can access this resource."
            )
        resp.raise_for_status()
        return resp.json()


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def list_issues(
    repo: str,
    state: str = "open",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """List issues for a GitHub repository.

    Args:
        repo: "owner/name", e.g. "ggml-org/llama.cpp"
        state: "open", "closed", or "all"
        limit: max issues to return (1-100)
    """
    if "/" not in repo:
        raise ValueError('repo must be "owner/name", e.g. "ggml-org/llama.cpp"')
    limit = max(1, min(limit, 100))
    owner, name = repo.split("/", 1)
    data = await _get(f"/repos/{owner}/{name}/issues", {"state": state, "per_page": limit})
    return [
        {
            "number": i["number"],
            "title": i["title"],
            "state": i["state"],
            "url": i["html_url"],
            "labels": [lab["name"] for lab in i.get("labels", [])],
            "is_pull_request": "pull_request" in i,
        }
        for i in data
    ]


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def search_code(query: str, repo: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """Search code across GitHub (or scoped to one repo).

    Args:
        query: search terms, e.g. "GGML_CPU_KLEIDIAI"
        repo: optional "owner/name" to scope the search
        limit: max results (1-50)
    """
    limit = max(1, min(limit, 50))
    q = query if not repo else f"{query} repo:{repo}"
    data = await _get("/search/code", {"q": q, "per_page": limit})
    return [
        {"path": item["path"], "repo": item["repository"]["full_name"], "url": item["html_url"]}
        for item in data.get("items", [])
    ]


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_repo(repo: str) -> dict[str, Any]:
    """Fetch metadata for a repo (stars, description, default branch, license)."""
    if "/" not in repo:
        raise ValueError('repo must be "owner/name", e.g. "ggml-org/llama.cpp"')
    owner, name = repo.split("/", 1)
    data = await _get(f"/repos/{owner}/{name}")
    return {
        "full_name": data["full_name"],
        "description": data.get("description"),
        "stars": data["stargazers_count"],
        "default_branch": data["default_branch"],
        "license": (data.get("license") or {}).get("spdx_id"),
        "url": data["html_url"],
    }


if __name__ == "__main__":
    mcp.run()
