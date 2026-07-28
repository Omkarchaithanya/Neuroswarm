"""MCP Server Manager — persistent sessions, discovery, reconcile, secure execute.

Enabled only when NSA_MCP_EXECUTE=1. Semantic routing may still use YAML schemas;
tools/call and schema injection for execute require successful tools/list reconcile.
"""

from __future__ import annotations

import atexit
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .mcp_env import (
    build_mcp_child_env,
    destructive_approved,
    tool_requires_destructive_approval,
)

_LOG = logging.getLogger(__name__)

_FAIL_LIMIT = 3
MCP_PROTOCOL_VERSION = "2025-11-25"
_RESULT_MAX_BYTES = int(os.getenv("NSA_MCP_RESULT_MAX_BYTES", str(512 * 1024)))
_MAX_INFLIGHT_PER_SERVER = int(os.getenv("NSA_MCP_MAX_INFLIGHT", "2"))


def mcp_execute_enabled() -> bool:
    raw = os.getenv("NSA_MCP_EXECUTE", "")
    return raw in {"1", "true", "True", "yes", "YES"}


@dataclass(slots=True)
class McpServerSpec:
    server_id: str
    script: Path
    cwd: Path
    transport: str = "stdio"  # stdio | http
    http_url: str | None = None


@dataclass
class _McpServerConn:
    spec: McpServerSpec
    proc: asyncio.subprocess.Process | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    next_id: int = 1
    fail_count: int = 0
    degraded: bool = False
    initialized: bool = False
    tools_list: list[dict[str, Any]] = field(default_factory=list)
    catalog_hash: str = ""
    restart_backoff_s: float = 0.5
    last_restart_at: float = 0.0
    inflight: asyncio.Semaphore = field(
        default_factory=lambda: asyncio.Semaphore(_MAX_INFLIGHT_PER_SERVER)
    )
    http_session: Any | None = None  # StreamableHttpSession when transport=http


# Registry leaf names → FastMCP function names when they historically differed.
TOOL_NAME_ALIASES: dict[str, str] = {
    "send_message": "post_message",
    "open_page": "navigate",
    "list_objects_v2": "list_objects",
    "extract": "extract_links",
}


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
    # Optional HTTP remotes: NSA_MCP_HTTP_<SERVER>=https://...
    for key, val in os.environ.items():
        if key.startswith("NSA_MCP_HTTP_") and val.strip():
            sid = key[len("NSA_MCP_HTTP_") :].lower().replace("_", "-")
            out[sid] = McpServerSpec(
                server_id=sid,
                script=Path("."),
                cwd=Path("."),
                transport="http",
                http_url=val.strip(),
            )
    return out


def _server_for_tool(tool_id: str, servers: dict[str, McpServerSpec]) -> McpServerSpec | None:
    tid = tool_id.lower()
    if "." in tid:
        prefix = tid.split(".", 1)[0]
        if prefix == "web" and "web-search" in servers:
            return servers["web-search"]
        if prefix in servers:
            return servers[prefix]
    for sid, spec in servers.items():
        if tid == sid or tid.startswith(sid.replace("-", ".") + ".") or sid in tid:
            return spec
    return None


def _mcp_tool_name(tool_id: str) -> str:
    if "." in tool_id:
        leaf = tool_id.split(".", 1)[-1]
    else:
        leaf = tool_id
    return TOOL_NAME_ALIASES.get(leaf, leaf)


def _hash_tools(tools: list[dict[str, Any]]) -> str:
    blob = json.dumps(tools, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class StreamableHttpSession:
    """Minimal Streamable HTTP MCP client (JSON-RPC over HTTP POST)."""

    def __init__(self, url: str) -> None:
        self.url = url.rstrip("/")
        self.next_id = 1
        self.initialized = False
        self.tools_list: list[dict[str, Any]] = []
        self.catalog_hash = ""

    async def initialize(self, *, timeout_s: float) -> None:
        import httpx

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            payload = {
                "jsonrpc": "2.0",
                "id": self.next_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "neuroswarm-router", "version": "1.0"},
                },
            }
            self.next_id += 1
            resp = await client.post(self.url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(str(data["error"]))
            await client.post(
                self.url,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
            list_payload = {
                "jsonrpc": "2.0",
                "id": self.next_id,
                "method": "tools/list",
                "params": {},
            }
            self.next_id += 1
            lr = await client.post(self.url, json=list_payload)
            lr.raise_for_status()
            listed = lr.json().get("result") or {}
            self.tools_list = list(listed.get("tools") or [])
            self.catalog_hash = _hash_tools(self.tools_list)
            self.initialized = True

    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, timeout_s: float
    ) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            payload = {
                "jsonrpc": "2.0",
                "id": self.next_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            }
            self.next_id += 1
            resp = await client.post(self.url, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def close(self) -> None:
        self.initialized = False


class McpServerManager:
    """Persistent MCP sessions with discovery, reconcile metadata, env allowlists."""

    def __init__(self) -> None:
        self._conns: dict[str, _McpServerConn] = {}
        self._servers_cache: dict[str, McpServerSpec] | None = None
        self._servers_root: Path | None = None
        self._spawn_count: int = 0
        # tool_id → executable after reconcile
        self.executable_tools: set[str] = set()
        self.discovered_by_server: dict[str, list[str]] = {}
        self.catalog_hash: str = ""
        self.protocol_version: str = MCP_PROTOCOL_VERSION
        self._reconcile_version: int = 0
        self._skipped_missing_deps: dict[str, str] = {}
        self._discover_errors: dict[str, str] = {}

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

    def status(self) -> dict[str, Any]:
        advertised = sum(len(v) for v in self.discovered_by_server.values())
        return {
            "protocol": self.protocol_version,
            "sessions": len(self._conns),
            "catalog_hash": self.catalog_hash,
            "tools_advertised": advertised,
            "tools_executable": len(self.executable_tools),
            "executable_count": len(self.executable_tools),
            "reconcile_version": self._reconcile_version,
            "discovered_by_server": {k: len(v) for k, v in self.discovered_by_server.items()},
            "skipped_missing_deps": dict(getattr(self, "_skipped_missing_deps", {}) or {}),
            "discover_errors": dict(getattr(self, "_discover_errors", {}) or {}),
        }

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
        if conn.http_session is not None:
            try:
                await conn.http_session.close()
            except Exception:
                pass
            conn.http_session = None
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

    async def _spawn_and_init(
        self,
        conn: _McpServerConn,
        *,
        timeout_s: float,
        tenant_id: str | None = None,
    ) -> None:
        spec = conn.spec
        # Backoff after failures
        now = time.monotonic()
        wait = conn.restart_backoff_s
        if conn.last_restart_at and (now - conn.last_restart_at) < wait:
            await asyncio.sleep(wait - (now - conn.last_restart_at))
        conn.last_restart_at = time.monotonic()

        if spec.transport == "http" and spec.http_url:
            sess = StreamableHttpSession(spec.http_url)
            await sess.initialize(timeout_s=timeout_s)
            conn.http_session = sess
            conn.tools_list = sess.tools_list
            conn.catalog_hash = sess.catalog_hash
            conn.initialized = True
            self.discovered_by_server[spec.server_id] = [
                str(t.get("name") or "") for t in conn.tools_list
            ]
            return

        env = build_mcp_child_env(spec.server_id, tenant_id=tenant_id)
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(spec.script),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(spec.cwd),
            env=env,
        )
        self._spawn_count += 1
        conn.proc = proc
        conn.next_id = 1
        assert proc.stdin and proc.stdout
        init = await self._rpc(
            conn,
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "clientInfo": {"name": "neuroswarm-router", "version": "1.0"},
            },
            timeout_s=timeout_s,
        )
        if "error" in init:
            raise RuntimeError(f"initialize failed: {init['error']}")
        note = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        proc.stdin.write(note.encode("utf-8"))
        await proc.stdin.drain()
        listed = await self._rpc(conn, "tools/list", {}, timeout_s=timeout_s)
        if "error" in listed:
            _LOG.warning("tools/list failed for %s: %s", spec.server_id, listed["error"])
            conn.tools_list = []
        else:
            result = listed.get("result") or {}
            conn.tools_list = list(result.get("tools") or [])
        conn.catalog_hash = _hash_tools(conn.tools_list)
        self.discovered_by_server[spec.server_id] = [
            str(t.get("name") or "") for t in conn.tools_list
        ]
        conn.initialized = True
        conn.restart_backoff_s = min(8.0, max(0.5, conn.restart_backoff_s * 1.5))

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
        # Read until matching id (skip notifications e.g. tools/list_changed)
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError("MCP RPC timeout")
            raw = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
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
            msg = json.loads(raw.decode("utf-8"))
            if msg.get("method") == "notifications/tools/list_changed":
                await self._handle_list_changed(conn)
                continue
            if msg.get("id") == msg_id:
                return msg
            # Unrelated notification — ignore
            if "id" not in msg and msg.get("method"):
                continue
            return msg

    async def _handle_list_changed(self, conn: _McpServerConn) -> None:
        try:
            listed = await self._rpc(conn, "tools/list", {}, timeout_s=15.0)
            result = listed.get("result") or {}
            conn.tools_list = list(result.get("tools") or [])
            conn.catalog_hash = _hash_tools(conn.tools_list)
            self.discovered_by_server[conn.spec.server_id] = [
                str(t.get("name") or "") for t in conn.tools_list
            ]
            self._reconcile_version += 1
            self._recompute_catalog_hash()
        except Exception as exc:
            _LOG.warning("list_changed re-list failed: %s", exc)

    def _recompute_catalog_hash(self) -> None:
        merged: list[dict[str, Any]] = []
        for conn in self._conns.values():
            merged.extend(conn.tools_list)
        self.catalog_hash = _hash_tools(merged)

    def reconcile_registry_ids(self, tool_ids: list[str]) -> set[str]:
        """Mark tool_ids executable when leaf name appears in a live tools/list."""
        discovered: set[str] = set()
        for names in self.discovered_by_server.values():
            discovered.update(n for n in names if n)
        executable: set[str] = set()
        for tid in tool_ids:
            leaf = _mcp_tool_name(tid)
            if leaf in discovered:
                executable.add(tid)
        self.executable_tools = executable
        self._reconcile_version += 1
        self._recompute_catalog_hash()
        return executable

    def is_executable(self, tool_id: str) -> bool:
        if not self.executable_tools:
            # Before any reconcile, deny execute when execute is on
            return False
        return tool_id in self.executable_tools

    async def ensure(
        self,
        spec: McpServerSpec,
        *,
        timeout_s: float = 30.0,
        tenant_id: str | None = None,
    ) -> _McpServerConn:
        conn = self._conn(spec)
        async with conn.lock:
            if conn.degraded:
                return conn
            if self._proc_alive(conn.proc) and conn.initialized:
                return conn
            if conn.http_session is not None and conn.initialized:
                return conn
            await self._kill_conn(conn)
            await self._spawn_and_init(conn, timeout_s=timeout_s, tenant_id=tenant_id)
            return conn

    async def discover_all(
        self,
        *,
        root: Path | None = None,
        timeout_s: float = 30.0,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        servers = self.servers(root)
        self._skipped_missing_deps: dict[str, str] = {}
        self._discover_errors: dict[str, str] = {}
        for spec in servers.values():
            try:
                await self.ensure(spec, timeout_s=timeout_s, tenant_id=tenant_id)
            except Exception as exc:
                msg = str(exc)
                missing = "ModuleNotFoundError" in msg or "No module named" in msg
                if missing:
                    # Optional servers (browser/postgres/s3) without pip deps — not a gateway fault.
                    brief = msg.strip().splitlines()[-1] if msg.strip() else msg
                    self._skipped_missing_deps[spec.server_id] = brief[:240]
                    _LOG.info("discover skipped for %s (missing dep): %s", spec.server_id, brief[:160])
                else:
                    self._discover_errors[spec.server_id] = msg[:240]
                    _LOG.warning("discover failed for %s: %s", spec.server_id, msg[:200])
        self._recompute_catalog_hash()
        return self.status()

    async def call(
        self,
        spec: McpServerSpec,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        timeout_s: float = 30.0,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        conn = self._conn(spec)
        async with conn.inflight:
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
                    if reinit or not (
                        (self._proc_alive(conn.proc) or conn.http_session)
                        and conn.initialized
                    ):
                        await self._kill_conn(conn)
                        await self._spawn_and_init(
                            conn, timeout_s=timeout_s, tenant_id=tenant_id
                        )
                    if conn.http_session is not None:
                        result = await conn.http_session.call_tool(
                            tool_name, arguments or {}, timeout_s=timeout_s
                        )
                    else:
                        result = await self._rpc(
                            conn,
                            "tools/call",
                            {"name": tool_name, "arguments": arguments or {}},
                            timeout_s=timeout_s,
                        )
                    if "error" in result:
                        raise RuntimeError(str(result["error"]))
                    payload = result.get("result")
                    raw = json.dumps(payload, default=str)
                    if len(raw.encode("utf-8")) > _RESULT_MAX_BYTES:
                        raise RuntimeError("MCP result exceeds NSA_MCP_RESULT_MAX_BYTES")
                    return {
                        "ok": True,
                        "server": spec.server_id,
                        "tool": tool_name,
                        "result": payload,
                        "catalog_hash": conn.catalog_hash,
                    }

                last_exc: Exception | None = None
                for attempt in range(2):
                    try:
                        out = await _one_shot(reinit=(attempt > 0))
                        conn.fail_count = 0
                        conn.restart_backoff_s = 0.5
                        return out
                    except asyncio.CancelledError:
                        await self._kill_conn(conn)
                        raise
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
        self._conns.clear()
        self._spawn_count = 0
        self.executable_tools.clear()
        self.discovered_by_server.clear()
        self.catalog_hash = ""
        self.invalidate_servers_cache()


# Back-compat aliases
McpProcessPool = McpServerManager

_POOL = McpServerManager()


def get_mcp_pool() -> McpServerManager:
    return _POOL


def get_mcp_manager() -> McpServerManager:
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
    pool: McpServerManager | None = None,
    approve: bool | None = None,
    tenant_id: str | None = None,
    require_reconciled: bool = True,
) -> dict[str, Any]:
    """Async MCP tools/call via the manager (warm session + policy)."""
    if not mcp_execute_enabled():
        return {
            "ok": False,
            "error": "MCP execute disabled. Set NSA_MCP_EXECUTE=1 to enable template server calls.",
            "tool_id": tool_id,
        }
    mgr = pool or _POOL
    if require_reconciled and not mgr.is_executable(tool_id):
        return {
            "ok": False,
            "error": "not_reconciled",
            "detail": (
                f"tool_id={tool_id} is not executable until reconciled against live tools/list. "
                "Run manager.discover_all + reconcile_registry_ids."
            ),
            "tool_id": tool_id,
        }
    if tool_requires_destructive_approval(tool_id, arguments):
        if not destructive_approved(approve=approve):
            return {
                "ok": False,
                "error": "destructive_approval_required",
                "detail": (
                    "Set NSA_MCP_APPROVE_DESTRUCTIVE=1 or pass approve=true for destructive tools."
                ),
                "tool_id": tool_id,
            }
        _LOG.info("mcp_destructive_approved tool_id=%s tenant=%s", tool_id, tenant_id)

    servers = mgr.servers(root)
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
        from .telemetry import mcp_span_attrs

        span_attrs = mcp_span_attrs(
            method="tools/call",
            session_id=f"{spec.server_id}:{tool_name}",
            protocol_version=MCP_PROTOCOL_VERSION,
        )
    except Exception:
        span_attrs = {}
    try:
        tracer = None
        try:
            from opentelemetry import trace

            tracer = trace.get_tracer("router")
        except Exception:
            tracer = None
        if tracer is not None:
            with tracer.start_as_current_span("mcp.tools.call", attributes=span_attrs):
                out = await mgr.call(
                    spec, tool_name, arguments or {}, timeout_s=timeout_s, tenant_id=tenant_id
                )
        else:
            out = await mgr.call(
                spec, tool_name, arguments or {}, timeout_s=timeout_s, tenant_id=tenant_id
            )
        if not out.get("ok"):
            out = dict(out)
            out.setdefault("tool_id", tool_id)
            out.setdefault("mcp_tool", tool_name)
        if span_attrs:
            out = dict(out)
            out.setdefault("otel", span_attrs)
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
    pool: McpServerManager | None = None,
    approve: bool | None = None,
    tenant_id: str | None = None,
    require_reconciled: bool = True,
) -> dict[str, Any]:
    """Sync facade for tests; prefer ``await call_tool`` from async callers."""
    kwargs = dict(
        root=root,
        timeout_s=timeout_s,
        pool=pool,
        approve=approve,
        tenant_id=tenant_id,
        require_reconciled=require_reconciled,
    )
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(call_tool(tool_id, arguments, **kwargs))
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(
            lambda: asyncio.run(call_tool(tool_id, arguments, **kwargs))
        )
        return fut.result()
