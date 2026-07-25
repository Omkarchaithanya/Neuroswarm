"""Optional thin MCP tools/call for template FastMCP servers.

Enabled only when NSA_MCP_EXECUTE=1. The semantic router remains a schema
selector; this module is a demo/execute sidecar, not a transparent MCP proxy.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def mcp_execute_enabled() -> bool:
    raw = os.getenv("NSA_MCP_EXECUTE", "")
    return raw in {"1", "true", "True", "yes", "YES"}


@dataclass(slots=True)
class McpServerSpec:
    server_id: str
    script: Path
    cwd: Path


def _templates_root() -> Path:
    env = os.getenv("NSA_TOOL_METADATA_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "templates" / "mcp-servers"


def discover_template_servers(root: Path | None = None) -> dict[str, McpServerSpec]:
    root = root or _templates_root()
    out: dict[str, McpServerSpec] = {}
    if not root.exists():
        return out
    for server_py in root.glob("*/server.py"):
        sid = server_py.parent.name
        out[sid] = McpServerSpec(server_id=sid, script=server_py, cwd=server_py.parent)
    return out


def _server_for_tool(tool_id: str, servers: dict[str, McpServerSpec]) -> McpServerSpec | None:
    tid = tool_id.lower()
    if "." in tid:
        prefix = tid.split(".", 1)[0]
        # web.search → web-search folder
        if prefix == "web" and "web-search" in servers:
            return servers["web-search"]
        if prefix in servers:
            return servers[prefix]
    for sid, spec in servers.items():
        if tid == sid or tid.startswith(sid.replace("-", ".") + ".") or sid in tid:
            return spec
    return None


def _mcp_tool_name(tool_id: str) -> str:
    """Map registry id github.list_issues → list_issues (FastMCP function name)."""
    if "." in tool_id:
        return tool_id.split(".", 1)[-1]
    return tool_id


async def _call_stdio_mcp(
    spec: McpServerSpec,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Minimal JSON-RPC stdio client against a FastMCP/python MCP server."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(spec.script),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(spec.cwd),
        env=os.environ.copy(),
    )
    assert proc.stdin and proc.stdout

    async def _rpc(method: str, params: dict[str, Any] | None = None, msg_id: int = 1) -> dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            payload["params"] = params
        line = json.dumps(payload) + "\n"
        proc.stdin.write(line.encode("utf-8"))
        await proc.stdin.drain()
        raw = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout_s)
        if not raw:
            err = await proc.stderr.read()
            raise RuntimeError(f"MCP server closed stdout: {err.decode(errors='replace')[:500]}")
        return json.loads(raw.decode("utf-8"))

    try:
        # initialize handshake (tolerant of servers that ignore extras)
        init = await _rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "neuroswarm-router", "version": "1.0"},
            },
            msg_id=1,
        )
        if "error" in init:
            raise RuntimeError(f"initialize failed: {init['error']}")
        # notifications/initialized (no response required)
        note = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        proc.stdin.write(note.encode("utf-8"))
        await proc.stdin.drain()
        result = await _rpc(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
            msg_id=2,
        )
        if "error" in result:
            raise RuntimeError(str(result["error"]))
        return {"ok": True, "server": spec.server_id, "tool": tool_name, "result": result.get("result")}
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        try:
            await proc.wait()
        except Exception:
            pass


def call_tool(
    tool_id: str,
    arguments: dict[str, Any] | None = None,
    *,
    root: Path | None = None,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    if not mcp_execute_enabled():
        return {
            "ok": False,
            "error": "MCP execute disabled. Set NSA_MCP_EXECUTE=1 to enable template server calls.",
            "tool_id": tool_id,
        }
    servers = discover_template_servers(root)
    spec = _server_for_tool(tool_id, servers)
    if spec is None:
        return {
            "ok": False,
            "error": f"No template MCP server mapped for tool_id={tool_id}",
            "tool_id": tool_id,
            "servers": sorted(servers),
        }
    tool_name = _mcp_tool_name(tool_id)
    try:
        return asyncio.run(
            _call_stdio_mcp(spec, tool_name, arguments or {}, timeout_s=timeout_s)
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "tool_id": tool_id,
            "server": spec.server_id,
            "mcp_tool": tool_name,
        }
