from __future__ import annotations


def tool_payload(name: str, description: str, params: dict[str, str]) -> dict:
    return {"id": name, "name": name, "description": description, "params": params}


def open_page(url: str) -> dict:
    return tool_payload("browser.open_page", "Open a browser page", {"url": url})
