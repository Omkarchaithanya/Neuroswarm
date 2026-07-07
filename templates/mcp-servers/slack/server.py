from __future__ import annotations


def tool_payload(name: str, description: str, params: dict[str, str]) -> dict:
    return {"id": name, "name": name, "description": description, "params": params}


def send_message(channel: str, text: str) -> dict:
    return tool_payload("slack.send_message", f"Send to {channel}", {"channel": channel, "text": text})
