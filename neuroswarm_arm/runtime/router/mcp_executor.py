"""Optional thin MCP tools/call for template FastMCP servers.

Enabled only when NSA_MCP_EXECUTE=1. The semantic router remains a schema
selector; this module is a demo/execute sidecar, not a transparent MCP proxy.

Servers are kept alive in a process pool (spawn + initialize once per
server_id) instead of spawn-per-call.
"""

from __future__ import annotations

import atexit
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_FAIL_LIMIT = 3


def mcp_execute_enabled() -> bool:
    raw = os.getenv("NSA_MCP_EXECUTE", "")
    return raw in {"1", "true", "True", "yes", "YES"}


@dataclass(slots=True)
class McpServerSpec:
    server_id: str
    script: Path
    cwd: Path


@dataclass
class _McpServerConn:
    spec: McpServerSpec
    proc: asyncio.subprocess.Process | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    next_id: int = 1
    fail_count: int = 0
    degraded: bool = False
    initialized: bool = False


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


class McpProcessPool:
    """Persistent stdio MCP servers keyed by server_id."""

    def __init__(self) -> None:
        self._conns: dict[str, _McpServerConn] = {}
        self._servers_cache: dict[str, McpServerSpec] | None = None
        self._servers_root: Path | None = None
        self._spawn_count: int = 0  # test/observability

    def servers(self, root: Path | None = None) -> dict[str, McpServerSpec]:
        root = root or _templates_root()
        if self._servers_cache is not None and self._servers_root == root:
            return self._servers_cache
        self._servers_cache = discover_template_servers(root)
        self._servers_root = root
        return self._servers_cache

    def invalidate_servers_cache(self) -> None:
        self._servers_cache = None
        self._servers_root = None

    def _conn(self, spec: McpServerSpec) -> _McpServerConn:
        conn = self._conns.get(spec.server_id)
        if conn is None:
            conn = _McpServerConn(spec=spec)
            self._conns[spec.server_id] = conn
        else:
            conn.spec = spec
        return conn

    @staticmethod
    def _proc_alive(proc: asyncio.subprocess.Process | None) -> bool:
        return proc is not None and proc.returncode is None

    async def _kill_conn(self, conn: _McpServerConn) -> None:
        proc = conn.proc
        conn.proc = None
        conn.initialized = False
        if proc is None:
            return
        try:
            if proc.stdin:
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

    async def _spawn_and_init(self, conn: _McpServerConn, *, timeout_s: float) -> None:
        spec = conn.spec
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(spec.script),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(spec.cwd),
            env=os.environ.copy(),
        )
        self._spawn_count += 1
        conn.proc = proc
        conn.next_id = 1
        assert proc.stdin and proc.stdout
        init = await self._rpc(
            conn,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "neuroswarm-router", "version": "1.0"},
            },
            timeout_s=timeout_s,
        )
        if "error" in init:
            raise RuntimeError(f"initialize failed: {init['error']}")
        note = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        proc.stdin.write(note.encode("utf-8"))
        await proc.stdin.drain()
        conn.initialized = True

    async def _rpc(
        self,
        conn: _McpServerConn,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_s: float,
    ) -> dict[str, Any]:
        proc = conn.proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            raise RuntimeError("MCP process not running")
        msg_id = conn.next_id
        conn.next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            payload["params"] = params
        line = json.dumps(payload) + "\n"
        proc.stdin.write(line.encode("utf-8"))
        await proc.stdin.drain()
        raw = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout_s)
        if not raw:
            err = b""
            try:
                if proc.stderr:
                    err = await asyncio.wait_for(proc.stderr.read(), timeout=1.0)
            except Exception:
                pass
            raise RuntimeError(
                f"MCP server closed stdout: {err.decode(errors='replace')[:500]}"
            )
        return json.loads(raw.decode("utf-8"))

    async def ensure(self, spec: McpServerSpec, *, timeout_s: float = 30.0) -> _McpServerConn:
        conn = self._conn(spec)
        async with conn.lock:
            if conn.degraded:
                return conn
            if self._proc_alive(conn.proc) and conn.initialized:
                return conn
            await self._kill_conn(conn)
            await self._spawn_and_init(conn, timeout_s=timeout_s)
            return conn

    async def call(
        self,
        spec: McpServerSpec,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        timeout_s: float = 30.0,
    ) -> dict[str, Any]:
        conn = self._conn(spec)
        async with conn.lock:
            if conn.degraded:
                return {
                    "ok": False,
                    "error": f"MCP server {spec.server_id} degraded after {_FAIL_LIMIT} failures",
                    "server": spec.server_id,
                    "tool": tool_name,
                    "degraded": True,
                }

            async def _one_shot(*, reinit: bool) -> dict[str, Any]:
                if reinit or not (self._proc_alive(conn.proc) and conn.initialized):
                    await self._kill_conn(conn)
                    await self._spawn_and_init(conn, timeout_s=timeout_s)
                result = await self._rpc(
                    conn,
                    "tools/call",
                    {"name": tool_name, "arguments": arguments or {}},
                    timeout_s=timeout_s,
                )
                if "error" in result:
                    raise RuntimeError(str(result["error"]))
                return {
                    "ok": True,
                    "server": spec.server_id,
                    "tool": tool_name,
                    "result": result.get("result"),
                }

            last_exc: Exception | None = None
            for attempt in range(2):
                try:
                    out = await _one_shot(reinit=(attempt > 0))
                    conn.fail_count = 0
                    return out
                except Exception as exc:
                    last_exc = exc
                    await self._kill_conn(conn)
            conn.fail_count += 1
            if conn.fail_count >= _FAIL_LIMIT:
                conn.degraded = True
            return {
                "ok": False,
                "error": str(last_exc) if last_exc else "MCP call failed",
                "server": spec.server_id,
                "tool": tool_name,
                "degraded": conn.degraded,
            }

    async def close_all(self) -> None:
        for sid in list(self._conns):
            conn = self._conns.pop(sid)
            async with conn.lock:
                await self._kill_conn(conn)

    def reset_for_tests(self) -> None:
        """Drop connections without awaiting (unit tests)."""
        self._conns.clear()
        self._spawn_count = 0
        self.invalidate_servers_cache()


_POOL = McpProcessPool()


def get_mcp_pool() -> McpProcessPool:
    return _POOL


def _atexit_close() -> None:
    try:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_POOL.close_all())
        finally:
            loop.close()
    except Exception:
        pass


atexit.register(_atexit_close)


async def call_tool(
    tool_id: str,
    arguments: dict[str, Any] | None = None,
    *,
    root: Path | None = None,
    timeout_s: float = 30.0,
    pool: McpProcessPool | None = None,
) -> dict[str, Any]:
    """Async MCP tools/call via the warm process pool."""
    if not mcp_execute_enabled():
        return {
            "ok": False,
            "error": "MCP execute disabled. Set NSA_MCP_EXECUTE=1 to enable template server calls.",
            "tool_id": tool_id,
        }
    pool = pool or _POOL
    servers = pool.servers(root)
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
        out = await pool.call(spec, tool_name, arguments or {}, timeout_s=timeout_s)
        if not out.get("ok"):
            out = dict(out)
            out.setdefault("tool_id", tool_id)
            out.setdefault("mcp_tool", tool_name)
        return out
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "tool_id": tool_id,
            "server": spec.server_id,
            "mcp_tool": tool_name,
        }


def call_tool_sync(
    tool_id: str,
    arguments: dict[str, Any] | None = None,
    *,
    root: Path | None = None,
    timeout_s: float = 30.0,
    pool: McpProcessPool | None = None,
) -> dict[str, Any]:
    """Sync facade for tests; prefer ``await call_tool`` from async callers."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            call_tool(tool_id, arguments, root=root, timeout_s=timeout_s, pool=pool)
        )
    # Already inside a loop — run in a fresh thread loop to avoid nest conflicts.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(
            lambda: asyncio.run(
                call_tool(tool_id, arguments, root=root, timeout_s=timeout_s, pool=pool)
            )
        )
        return fut.result()
