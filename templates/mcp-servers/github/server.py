from __future__ import annotations


def tool_payload(name: str, description: str, params: dict[str, str]) -> dict:
    return {"id": name, "name": name, "description": description, "params": params}


def list_issues(repo: str, state: str = "open", limit: int = 10) -> dict:
    return tool_payload("github.list_issues", f"List issues for {repo}", {"state": state, "limit": str(limit)})
