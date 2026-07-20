"""Arm Performix MCP client — stdio Docker MCP or HTTP JSON-RPC bridge."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

LOG = logging.getLogger("nexus.performix.mcp")


class PerformixMCPClient:
    """Call Arm MCP tools (`apx_recipe_run`, `apx_recipe_compare`, `kb_search`)."""

    def __init__(
        self,
        *,
        mcp_url: str = "",
        stdio_command: list[str] | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        self.mcp_url = (mcp_url or "").rstrip("/")
        self.stdio_command = stdio_command
        self.timeout_s = timeout_s

    def list_tools(self) -> list[str]:
        return self._run(self._list_tools_async)

    def recipe_run(
        self,
        recipe: str,
        *,
        output: Path | None = None,
        duration: int | None = None,
        target: str | None = None,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {"recipe": recipe}
        if output is not None:
            args["output"] = str(output)
        if duration is not None:
            args["duration"] = duration
        if target:
            args["target"] = target
        return self._run(lambda: self._call_tool_async("apx_recipe_run", args))

    def recipe_compare(self, baseline: Path, optimized: Path, output: Path) -> dict[str, Any]:
        return self._run(
            lambda: self._call_tool_async(
                "apx_recipe_compare",
                {
                    "baseline": str(baseline),
                    "optimized": str(optimized),
                    "output": str(output),
                },
            )
        )

    def kb_search(self, query: str) -> dict[str, Any]:
        return self._run(lambda: self._call_tool_async("kb_search", {"query": query}))

    def _run(self, coro_factory) -> dict[str, Any] | list[str]:
        try:
            return asyncio.run(coro_factory())
        except RuntimeError:
            # Nested event loop (rare) — fall back to HTTP only
            if self.mcp_url.startswith("http"):
                return self._http_call("tools/list", {}) if coro_factory.__name__ == "<lambda>" else {}
            raise

    async def _list_tools_async(self) -> list[str]:
        if self.mcp_url.startswith("http"):
            data = self._http_call("tools/list", {})
            tools = data.get("tools") or data.get("result", {}).get("tools") or []
            return [t.get("name", "") for t in tools if isinstance(t, dict)]
        session = await self._stdio_session()
        if session is None:
            return []
        async with session:
            result = await session.list_tools()
            return [t.name for t in getattr(result, "tools", [])]

    async def _call_tool_async(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.mcp_url.startswith("http"):
            data = self._http_call("tools/call", {"name": name, "arguments": arguments})
            return data if isinstance(data, dict) else {"result": data}

        session = await self._stdio_session()
        if session is None:
            return {"ok": False, "error": "mcp_stdio_unavailable"}
        async with session:
            result = await session.call_tool(name, arguments)
            content = getattr(result, "content", None) or []
            texts: list[str] = []
            for item in content:
                text = getattr(item, "text", None)
                if text:
                    texts.append(text)
            payload: dict[str, Any] = {"ok": True, "tool": name, "texts": texts}
            if texts:
                try:
                    payload["parsed"] = json.loads(texts[0])
                except Exception:
                    payload["raw"] = texts[0]
            return payload

    async def _stdio_session(self):
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except Exception as exc:
            LOG.warning("mcp package unavailable: %s", exc)
            return None

        cmd = self.stdio_command
        if not cmd:
            # Default: docker run stdio against armlimited/arm-mcp
            image = os.getenv("ARM_MCP_IMAGE", "armlimited/arm-mcp:latest")
            cmd = [
                "docker",
                "run",
                "--rm",
                "-i",
                "--network",
                "host",
                image,
            ]
        params = StdioServerParameters(command=cmd[0], args=cmd[1:], env=dict(os.environ))
        # Caller must manage async with; return a context helper via nest
        # Use a short-lived session pattern:
        return _StdioSession(params, stdio_client, ClientSession)

    def _http_call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Best-effort JSON-RPC/HTTP bridge (if an HTTP wrapper is deployed)."""
        url = f"{self.mcp_url}/mcp" if not self.mcp_url.endswith("/mcp") else self.mcp_url
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return {"ok": False, "error": f"http_{exc.code}", "body": exc.read().decode("utf-8", "ignore")}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


class _StdioSession:
    def __init__(self, params, stdio_client, ClientSession) -> None:
        self._params = params
        self._stdio_client = stdio_client
        self._ClientSession = ClientSession
        self._cm = None
        self._session = None

    async def __aenter__(self):
        self._cm = self._stdio_client(self._params)
        read, write = await self._cm.__aenter__()
        self._session = self._ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        return self._session

    async def __aexit__(self, *exc):
        if self._session is not None:
            await self._session.__aexit__(*exc)
        if self._cm is not None:
            await self._cm.__aexit__(*exc)
