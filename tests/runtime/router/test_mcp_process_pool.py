"""Tests for persistent MCP process pool / server manager."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuroswarm_arm.runtime.router.mcp_executor import (
    McpProcessPool,
    McpServerSpec,
    call_tool,
    call_tool_sync,
)


@pytest.fixture
def pool() -> McpProcessPool:
    p = McpProcessPool()
    yield p
    p.reset_for_tests()


def test_mcp_execute_disabled_async(monkeypatch):
    monkeypatch.delenv("NSA_MCP_EXECUTE", raising=False)

    async def _run():
        out = await call_tool("github.list_issues", {"repo": "a/b"})
        assert out["ok"] is False
        assert "NSA_MCP_EXECUTE" in out["error"]

    asyncio.run(_run())


def test_call_tool_sync_disabled(monkeypatch):
    monkeypatch.delenv("NSA_MCP_EXECUTE", raising=False)
    out = call_tool_sync("github.list_issues", {"repo": "a/b"})
    assert out["ok"] is False


def _json_line(msg: dict) -> bytes:
    return (json.dumps(msg) + "\n").encode()


@pytest.mark.asyncio
async def test_pool_reuses_process_two_calls(pool: McpProcessPool, tmp_path: Path):
    script = tmp_path / "server.py"
    script.write_text("# fake\n", encoding="utf-8")
    spec = McpServerSpec(server_id="s3", script=script, cwd=tmp_path)

    fake_proc = MagicMock()
    fake_proc.returncode = None
    fake_proc.stdin = MagicMock()
    fake_proc.stdin.write = MagicMock()
    fake_proc.stdin.drain = AsyncMock()
    fake_proc.stdin.close = MagicMock()
    fake_proc.stdout = MagicMock()
    fake_proc.stderr = MagicMock()
    fake_proc.stderr.read = AsyncMock(return_value=b"")
    fake_proc.kill = MagicMock()
    fake_proc.wait = AsyncMock(return_value=0)

    # initialize (id=1), tools/list (id=2), tools/call (id=3), tools/call (id=4)
    responses = [
        _json_line({"jsonrpc": "2.0", "id": 1, "result": {}}),
        _json_line(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"tools": [{"name": "put_object"}, {"name": "get_object"}]},
            }
        ),
        _json_line({"jsonrpc": "2.0", "id": 3, "result": {"content": [{"text": "ok"}]}}),
        _json_line({"jsonrpc": "2.0", "id": 4, "result": {"content": [{"text": "ok2"}]}}),
    ]
    fake_proc.stdout.readline = AsyncMock(side_effect=responses)

    async def _spawn(*_a, **_k):
        return fake_proc

    with patch(
        "neuroswarm_arm.runtime.router.mcp_executor.asyncio.create_subprocess_exec",
        new=_spawn,
    ):
        out1 = await pool.call(spec, "put_object", {"bucket": "b"}, timeout_s=5.0)
        out2 = await pool.call(spec, "get_object", {"bucket": "b"}, timeout_s=5.0)

    assert out1["ok"] is True
    assert out2["ok"] is True
    assert pool._spawn_count == 1


@pytest.mark.asyncio
async def test_pool_degraded_after_three_fails(pool: McpProcessPool, tmp_path: Path):
    script = tmp_path / "server.py"
    script.write_text("# fake\n", encoding="utf-8")
    spec = McpServerSpec(server_id="slack", script=script, cwd=tmp_path)

    async def _boom(*_a, **_k):
        raise RuntimeError("spawn failed")

    with patch(
        "neuroswarm_arm.runtime.router.mcp_executor.asyncio.create_subprocess_exec",
        new=_boom,
    ):
        for _ in range(3):
            out = await pool.call(spec, "post_message", {}, timeout_s=1.0)
            assert out["ok"] is False
        out_fast = await pool.call(spec, "post_message", {}, timeout_s=1.0)

    assert out_fast["ok"] is False
    assert out_fast.get("degraded") is True
    assert "degraded" in out_fast["error"].lower()


@pytest.mark.asyncio
async def test_pool_lock_serializes(pool: McpProcessPool, tmp_path: Path):
    script = tmp_path / "server.py"
    script.write_text("# fake\n", encoding="utf-8")
    spec = McpServerSpec(server_id="github", script=script, cwd=tmp_path)

    in_flight = 0
    max_in_flight = 0

    fake_proc = MagicMock()
    fake_proc.returncode = None
    fake_proc.stdin = MagicMock()
    fake_proc.stdin.write = MagicMock()
    fake_proc.stdin.drain = AsyncMock()
    fake_proc.stdin.close = MagicMock()
    fake_proc.stdout = MagicMock()
    fake_proc.stderr = MagicMock()
    fake_proc.kill = MagicMock()
    fake_proc.wait = AsyncMock(return_value=0)

    seq = {"n": 0}

    async def _readline():
        seq["n"] += 1
        n = seq["n"]
        if n == 1:
            return _json_line({"jsonrpc": "2.0", "id": 1, "result": {}})
        if n == 2:
            return _json_line(
                {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "list_issues"}]}}
            )
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.08)
        in_flight -= 1
        return _json_line({"jsonrpc": "2.0", "id": n, "result": {"ok": True}})

    fake_proc.stdout.readline = _readline

    async def _spawn(*_a, **_k):
        return fake_proc

    with patch(
        "neuroswarm_arm.runtime.router.mcp_executor.asyncio.create_subprocess_exec",
        new=_spawn,
    ):
        await pool.ensure(spec, timeout_s=5.0)
        await asyncio.gather(
            pool.call(spec, "list_issues", {}, timeout_s=5.0),
            pool.call(spec, "create_issue", {}, timeout_s=5.0),
        )

    assert max_in_flight == 1


@pytest.mark.asyncio
async def test_call_tool_requires_reconcile(monkeypatch, pool: McpProcessPool):
    monkeypatch.setenv("NSA_MCP_EXECUTE", "1")
    out = await call_tool(
        "github.list_issues",
        {"repo": "a/b"},
        pool=pool,
        require_reconciled=True,
    )
    assert out["ok"] is False
    assert out["error"] == "not_reconciled"
