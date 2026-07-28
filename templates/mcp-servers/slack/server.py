"""Slack MCP server — FastMCP + slack_sdk AsyncWebClient.

Auth: export SLACK_BOT_TOKEN=xoxb-...
Tool names match templates/mcp-servers/slack/tools/*.tool.yaml IDs.
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
        needed = ""
        try:
            resp = exc.response
            if isinstance(resp, dict):
                needed = str(resp.get("needed") or "")
            elif resp is not None and hasattr(resp, "get"):
                needed = str(resp.get("needed") or "")
        except Exception:
            needed = ""
        hint = needed or "channels:read (list), chat:write (post), users:read (lookup)"
        return ValueError(f"Missing Slack OAuth scope. Add Bot Token Scope(s): {hint}. Then Reinstall to Workspace.")
    return ValueError(f"Slack API error: {err or exc}")


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def post_message(channel: str, text: str) -> dict[str, Any]:
    """Post a message to a Slack channel (chat.postMessage)."""
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


# Legacy FastMCP name (executor aliases send_message → post_message).
@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def send_message(channel: str, text: str) -> dict[str, Any]:
    """Legacy alias for post_message."""
    return await post_message(channel=channel, text=text)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def add_reaction(channel: str, timestamp: str, name: str) -> dict[str, Any]:
    """Add an emoji reaction to a message."""
    if not channel or not timestamp or not name:
        raise ValueError("channel, timestamp, and name are required")
    try:
        resp = await _client().reactions_add(channel=channel, timestamp=timestamp, name=name)
    except SlackApiError as exc:
        raise _map_slack_error(exc) from None
    data = resp.data if hasattr(resp, "data") else dict(resp)
    return {"ok": bool(data.get("ok")), "channel": channel, "timestamp": timestamp, "name": name}


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_user(user: str) -> dict[str, Any]:
    """Fetch a Slack user profile by user ID."""
    if not user:
        raise ValueError("user is required")
    try:
        resp = await _client().users_info(user=user)
    except SlackApiError as exc:
        raise _map_slack_error(exc) from None
    data = resp.data if hasattr(resp, "data") else dict(resp)
    u = data.get("user") or {}
    return {
        "id": u.get("id"),
        "name": u.get("name"),
        "real_name": u.get("real_name"),
        "is_bot": u.get("is_bot"),
    }


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def list_channels(limit: int = 100) -> list[dict[str, Any]]:
    """List conversations the bot can see."""
    limit = max(1, min(int(limit), 200))
    # public_channel needs channels:read; private_channel also needs groups:read.
    # Prefer public-only so a bot with channels:read works without groups:read.
    try:
        resp = await _client().conversations_list(limit=limit, types="public_channel")
    except SlackApiError as exc:
        raise _map_slack_error(exc) from None
    data = resp.data if hasattr(resp, "data") else dict(resp)
    return [
        {"id": c.get("id"), "name": c.get("name"), "is_private": c.get("is_private")}
        for c in (data.get("channels") or [])
    ]


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def search_messages(query: str, count: int = 20) -> dict[str, Any]:
    """Search messages (requires search:read scope on a user token for full results)."""
    if not query or not query.strip():
        raise ValueError("query is required")
    count = max(1, min(int(count), 100))
    try:
        resp = await _client().search_messages(query=query.strip(), count=count)
    except SlackApiError as exc:
        raise _map_slack_error(exc) from None
    data = resp.data if hasattr(resp, "data") else dict(resp)
    matches = ((data.get("messages") or {}).get("matches")) or []
    return {
        "query": query,
        "matches": [
            {"text": m.get("text"), "channel": (m.get("channel") or {}).get("name"), "ts": m.get("ts")}
            for m in matches
        ],
    }


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def set_topic(channel: str, topic: str) -> dict[str, Any]:
    """Set a channel topic."""
    if not channel:
        raise ValueError("channel is required")
    try:
        resp = await _client().conversations_setTopic(channel=channel, topic=topic or "")
    except SlackApiError as exc:
        raise _map_slack_error(exc) from None
    data = resp.data if hasattr(resp, "data") else dict(resp)
    return {"ok": bool(data.get("ok")), "channel": channel, "topic": topic}


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def upload_file(
    channels: str,
    content: str,
    filename: str = "upload.txt",
    title: str | None = None,
) -> dict[str, Any]:
    """Upload a text file to one or more channels (comma-separated IDs)."""
    if not channels or content is None:
        raise ValueError("channels and content are required")
    try:
        resp = await _client().files_upload_v2(
            channel=channels.split(",")[0].strip(),
            content=content,
            filename=filename,
            title=title or filename,
        )
    except SlackApiError as exc:
        raise _map_slack_error(exc) from None
    data = resp.data if hasattr(resp, "data") else dict(resp)
    return {"ok": bool(data.get("ok")), "file": data.get("file") or data.get("files")}


if __name__ == "__main__":
    mcp.run()
