"""GitHub MCP server — FastMCP + GitHub REST API v3.

Auth: export GITHUB_TOKEN=ghp_xxx (optional for public repos).
Tool names match templates/mcp-servers/github/tools/*.tool.yaml IDs.
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


async def _request(method: str, path: str, *, json_body: dict[str, Any] | None = None) -> Any:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.request(
            method, f"{GITHUB_API}{path}", headers=_headers(), json=json_body
        )
        if resp.status_code >= 400:
            raise ValueError(f"GitHub HTTP {resp.status_code}: {resp.text[:300]}")
        if resp.status_code == 204 or not resp.content:
            return {"ok": True}
        return resp.json()


def _split_repo(repo: str) -> tuple[str, str]:
    if "/" not in repo:
        raise ValueError('repo must be "owner/name", e.g. "ggml-org/llama.cpp"')
    owner, name = repo.split("/", 1)
    return owner, name


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
    """List issues for a GitHub repository."""
    limit = max(1, min(limit, 100))
    owner, name = _split_repo(repo)
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
    """Search code across GitHub (or scoped to one repo)."""
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
    owner, name = _split_repo(repo)
    data = await _get(f"/repos/{owner}/{name}")
    return {
        "full_name": data["full_name"],
        "description": data.get("description"),
        "stars": data["stargazers_count"],
        "default_branch": data["default_branch"],
        "license": (data.get("license") or {}).get("spdx_id"),
        "url": data["html_url"],
    }


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def create_issue(repo: str, title: str, body: str = "") -> dict[str, Any]:
    """Create an issue on a GitHub repository."""
    if not title:
        raise ValueError("title is required")
    owner, name = _split_repo(repo)
    data = await _request(
        "POST", f"/repos/{owner}/{name}/issues", json_body={"title": title, "body": body or ""}
    )
    return {
        "number": data.get("number"),
        "title": data.get("title"),
        "url": data.get("html_url"),
        "state": data.get("state"),
    }


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_file(repo: str, path: str, ref: str | None = None) -> dict[str, Any]:
    """Fetch a file's content metadata from a repository."""
    if not path:
        raise ValueError("path is required")
    owner, name = _split_repo(repo)
    params = {"ref": ref} if ref else None
    data = await _get(f"/repos/{owner}/{name}/contents/{path.lstrip('/')}", params)
    return {
        "path": data.get("path"),
        "sha": data.get("sha"),
        "size": data.get("size"),
        "encoding": data.get("encoding"),
        "content": data.get("content"),
        "url": data.get("html_url"),
    }


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def list_commits(repo: str, limit: int = 10, sha: str | None = None) -> list[dict[str, Any]]:
    """List recent commits for a repository."""
    limit = max(1, min(limit, 100))
    owner, name = _split_repo(repo)
    params: dict[str, Any] = {"per_page": limit}
    if sha:
        params["sha"] = sha
    data = await _get(f"/repos/{owner}/{name}/commits", params)
    return [
        {
            "sha": c.get("sha"),
            "message": (c.get("commit") or {}).get("message"),
            "author": ((c.get("commit") or {}).get("author") or {}).get("name"),
            "url": c.get("html_url"),
        }
        for c in data
    ]


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def list_pull_requests(
    repo: str, state: str = "open", limit: int = 10
) -> list[dict[str, Any]]:
    """List pull requests for a repository."""
    limit = max(1, min(limit, 100))
    owner, name = _split_repo(repo)
    data = await _get(
        f"/repos/{owner}/{name}/pulls", {"state": state, "per_page": limit}
    )
    return [
        {
            "number": p.get("number"),
            "title": p.get("title"),
            "state": p.get("state"),
            "url": p.get("html_url"),
            "user": (p.get("user") or {}).get("login"),
        }
        for p in data
    ]


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def search_issues(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search issues/PRs across GitHub."""
    if not query or not query.strip():
        raise ValueError("query is required")
    limit = max(1, min(limit, 50))
    data = await _get("/search/issues", {"q": query.strip(), "per_page": limit})
    return [
        {
            "number": item.get("number"),
            "title": item.get("title"),
            "state": item.get("state"),
            "url": item.get("html_url"),
            "repository": (item.get("repository_url") or "").rsplit("/", 2)[-2:],
        }
        for item in data.get("items", [])
    ]


if __name__ == "__main__":
    mcp.run()
