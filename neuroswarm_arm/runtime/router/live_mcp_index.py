"""Optional live MCP tools/list filter for router indexing.

When NSA_MCP_LIVE_INDEX=1, only keep ToolRecords whose server responds to
tools/list (via MCP executor). Static YAML index remains the default (flag=0).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Iterable

from .models import ToolRecord

_LOG = logging.getLogger(__name__)


def live_index_enabled() -> bool:
    raw = os.getenv("NSA_MCP_LIVE_INDEX", "0")
    return raw in {"1", "true", "True", "yes", "YES"}


def _server_id_from_tool(tool: ToolRecord) -> str:
    ns = str(getattr(tool, "namespace", "") or "")
    if ns:
        return ns.split(".")[0].split("/")[0]
    tid = str(getattr(tool, "id", "") or "")
    if "." in tid:
        return tid.split(".", 1)[0]
    if "/" in tid:
        return tid.split("/", 1)[0]
    return ""


def filter_tools_by_live_mcp(tools: Iterable[ToolRecord], *, timeout_s: float = 25.0) -> list[ToolRecord]:
    """Drop tools whose MCP server fails tools/list. Returns list (may be empty)."""
    items = list(tools)
    if not items:
        return []
    try:
        return asyncio.run(_filter_async(items, timeout_s=timeout_s))
    except RuntimeError:
        _LOG.warning("NSA_MCP_LIVE_INDEX: event loop running; keeping static tools")
        return items
    except Exception as exc:
        _LOG.warning("NSA_MCP_LIVE_INDEX probe failed (%s); keeping static tools", exc)
        return items


async def _filter_async(tools: list[ToolRecord], *, timeout_s: float) -> list[ToolRecord]:
    from .mcp_executor import McpServerManager

    mgr = McpServerManager()
    try:
        status = await mgr.discover_all(timeout_s=timeout_s)
        live_servers = {
            sid
            for sid, names in (mgr.discovered_by_server or {}).items()
            if names
        }
        live_leaf_names: set[str] = set()
        for names in (mgr.discovered_by_server or {}).values():
            live_leaf_names.update(n for n in names if n)
        _LOG.info(
            "NSA_MCP_LIVE_INDEX discover status=%s live_servers=%s",
            {k: status.get(k) for k in ("tools_advertised", "sessions", "discover_errors") if isinstance(status, dict)},
            sorted(live_servers),
        )
    finally:
        try:
            await mgr.close_all()
        except Exception:
            pass

    if not live_servers:
        _LOG.warning("NSA_MCP_LIVE_INDEX: zero live servers — index empty")
        return []

    kept: list[ToolRecord] = []
    for tool in tools:
        sid = _server_id_from_tool(tool)
        leaf = str(getattr(tool, "name", "") or "")
        if sid and sid not in live_servers:
            continue
        if live_leaf_names and leaf:
            if leaf not in live_leaf_names and not any(
                leaf.endswith(n) or n.endswith(leaf) for n in live_leaf_names
            ):
                continue
        kept.append(tool)
    _LOG.info(
        "NSA_MCP_LIVE_INDEX: kept %d/%d tools from live servers=%s",
        len(kept),
        len(tools),
        sorted(live_servers),
    )
    return kept
