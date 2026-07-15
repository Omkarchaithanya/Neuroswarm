from __future__ import annotations


def tool_payload(name: str, description: str, params: dict[str, str]) -> dict:
    return {
        "id": name,
        "name": name,
        "description": description,
        "params": params,
    }
