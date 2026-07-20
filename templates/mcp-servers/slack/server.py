"""Slack MCP server — REAL implementation (FastMCP + slack_sdk AsyncWebClient).

Replaces the fake stub that only echoed its own tool description back.
Auth: export SLACK_BOT_TOKEN=xoxb-... (bot token with chat:write and
channels:history / groups:history as needed for the channels you use).

Run: python server.py          (stdio, for local MCP clients)
Test: npx @modelcontextprotocol/inspector python server.py
"""
from __future__ import annotations

import os
from typing import Any

from fastmcp import FastMCP
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

TOKEN = os.environ.get("SLACK_BOT_TOKEN")

mcp = FastMCP("slack")


def _client() -> AsyncWebClient:
    if not TOKEN:
        raise ValueError(
            "SLACK_BOT_TOKEN is not set. Export a bot token (xoxb-...) before calling Slack tools."
        )
    return AsyncWebClient(token=TOKEN)


def _map_slack_error(exc: SlackApiError) -> ValueError:
    err = ""
    try:
        resp = exc.response
        if isinstance(resp, dict):
            err = str(resp.get("error") or "")
        elif resp is not None and "error" in resp:
            err = str(resp["error"])
        else:
            err = str(exc)
    except Exception:
        err = str(exc)
    err_l = err.lower()
    if err_l in ("channel_not_found",):
        return ValueError(
            "Slack channel not found. Use a channel ID (C…) or public channel name the bot can see."
        )
    if err_l in ("not_in_channel",):
        return ValueError(
            "Bot is not in that channel. Invite the bot (/invite @bot) then retry."
        )
    if err_l in ("ratelimited", "rate_limited"):
        return ValueError("Slack rate limit hit. Wait and retry; reduce message frequency.")
    if err_l in ("invalid_auth", "not_authed", "account_inactive", "token_revoked", "token_expired"):
        return ValueError(
            "Slack auth failed. Check SLACK_BOT_TOKEN is a valid xoxb- bot token and not revoked."
        )
    if err_l in ("missing_scope",):
        return ValueError(
            "Missing Slack OAuth scope. Add chat:write and channels:history (and groups:history if private)."
        )
    return ValueError(f"Slack API error: {err or exc}")


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def send_message(channel: str, text: str) -> dict[str, Any]:
    """Post a message to a Slack channel (chat.postMessage).

    Args:
        channel: channel ID (C…) or name
        text: message body
    """
    if not channel or not text:
        raise ValueError("channel and text are required")
    try:
        resp = await _client().chat_postMessage(channel=channel, text=text)
    except SlackApiError as exc:
        raise _map_slack_error(exc) from None
    data = resp.data if hasattr(resp, "data") else dict(resp)
    return {
        "ok": bool(data.get("ok")),
        "channel": data.get("channel"),
        "ts": data.get("ts"),
        "message": (data.get("message") or {}).get("text"),
    }


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_history(channel: str, limit: int = 20) -> list[dict[str, Any]]:
    """Fetch recent messages from a channel (conversations.history).

    Args:
        channel: channel ID (C…)
        limit: max messages (1-100)
    """
    if not channel:
        raise ValueError("channel is required")
    limit = max(1, min(int(limit), 100))
    try:
        resp = await _client().conversations_history(channel=channel, limit=limit)
    except SlackApiError as exc:
        raise _map_slack_error(exc) from None
    data = resp.data if hasattr(resp, "data") else dict(resp)
    messages = data.get("messages") or []
    return [
        {
            "ts": m.get("ts"),
            "user": m.get("user"),
            "text": m.get("text"),
            "type": m.get("type"),
        }
        for m in messages
    ]


if __name__ == "__main__":
    mcp.run()
