from __future__ import annotations


def tool_payload(name: str, description: str, params: dict[str, str]) -> dict:
    return {"id": name, "name": name, "description": description, "params": params}


def query(sql: str) -> dict:
    return tool_payload("postgres.query", "Run a read-only SQL query", {"sql": sql})
