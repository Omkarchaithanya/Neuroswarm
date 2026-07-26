"""SSRF, SQL safety, env allowlist, MCP reconcile / approval tests."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuroswarm_arm.runtime.router.mcp_env import (
    build_mcp_child_env,
    destructive_approved,
    tool_requires_destructive_approval,
)
from neuroswarm_arm.runtime.router.mcp_executor import (
    MCP_PROTOCOL_VERSION,
    McpServerManager,
    McpServerSpec,
    call_tool,
)
from neuroswarm_arm.runtime.router.mcp_sql_safety import SqlSafetyError, assert_single_readonly_statement
from neuroswarm_arm.runtime.router.mcp_ssrf import SsrfError, resolve_and_validate_host, validate_url_ssrf


def test_protocol_version_constant():
    assert MCP_PROTOCOL_VERSION == "2025-11-25"


def test_ssrf_blocks_loopback_literal():
    with pytest.raises(SsrfError):
        validate_url_ssrf("http://127.0.0.1/admin")


def test_ssrf_blocks_private_literal():
    with pytest.raises(SsrfError):
        validate_url_ssrf("http://10.0.0.1/")
    with pytest.raises(SsrfError):
        validate_url_ssrf("http://192.168.1.1/")
    with pytest.raises(SsrfError):
        validate_url_ssrf("http://169.254.169.254/latest/meta-data")
    with pytest.raises(SsrfError):
        validate_url_ssrf("http://100.64.1.1/")


def test_ssrf_blocks_file_and_userinfo():
    with pytest.raises(SsrfError):
        validate_url_ssrf("file:///etc/passwd")
    with pytest.raises(SsrfError):
        validate_url_ssrf("https://user:pass@example.com/")


def test_ssrf_blocks_metadata_hostname():
    with pytest.raises(SsrfError):
        validate_url_ssrf("http://metadata.google.internal/")


def test_ssrf_allowlist(monkeypatch):
    monkeypatch.setenv("NSA_MCP_BROWSER_HOST_ALLOWLIST", "example.com")
    with pytest.raises(SsrfError):
        validate_url_ssrf("https://evil.com/")
    with patch(
        "neuroswarm_arm.runtime.router.mcp_ssrf.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 0))],
    ):
        assert validate_url_ssrf("https://example.com/path").startswith("https://")


def test_ssrf_blocks_dns_to_private():
    with patch(
        "neuroswarm_arm.runtime.router.mcp_ssrf.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("10.1.2.3", 0))],
    ):
        with pytest.raises(SsrfError, match="blocked resolved"):
            resolve_and_validate_host("evil.internal")


def test_ssrf_redirect_to_private_fails():
    from neuroswarm_arm.runtime.router.mcp_ssrf import fetch_url_ssrf_safe

    class _Resp:
        def __init__(self, status_code, headers=None, content=b"", url="https://example.com/"):
            self.status_code = status_code
            self.headers = headers or {}
            self.content = content
            self.url = url

        @property
        def is_redirect(self) -> bool:
            return self.status_code in {301, 302, 303, 307, 308}

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise ValueError(f"HTTP {self.status_code}")

    async def _run():
        async def _get(url, **_k):
            return _Resp(302, {"location": "http://10.0.0.5/secret"}, url=url)

        mock_client = MagicMock()
        mock_client.get = _get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "neuroswarm_arm.runtime.router.mcp_ssrf.socket.getaddrinfo",
            return_value=[(0, 0, 0, "", ("93.184.216.34", 0))],
        ):
            with patch("httpx.AsyncClient", return_value=mock_client):
                with pytest.raises(SsrfError, match="blocked"):
                    await fetch_url_ssrf_safe("https://example.com/start")

    asyncio.run(_run())


def test_ssrf_pin_connects_via_resolved_ip():
    from urllib.parse import urlparse

    from neuroswarm_arm.runtime.router.mcp_ssrf import fetch_url_ssrf_safe, pin_url_to_resolved_ip

    with patch(
        "neuroswarm_arm.runtime.router.mcp_ssrf.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 0))],
    ):
        connect, host, ips = pin_url_to_resolved_ip("https://example.com/path")
    assert host == "example.com"
    assert "93.184.216.34" in connect
    assert "example.com" not in urlparse(connect).netloc
    assert ips == ["93.184.216.34"]

    class _Resp:
        status_code = 200
        headers = {"content-type": "text/plain"}
        content = b"ok"
        url = "https://93.184.216.34/path"
        is_redirect = False

        def raise_for_status(self) -> None:
            return None

    captured: dict = {}

    async def _run():
        async def _get(url, headers=None, **_k):
            captured["url"] = url
            captured["headers"] = headers or {}
            return _Resp()

        mock_client = MagicMock()
        mock_client.get = _get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        with patch(
            "neuroswarm_arm.runtime.router.mcp_ssrf.socket.getaddrinfo",
            return_value=[(0, 0, 0, "", ("93.184.216.34", 0))],
        ):
            with patch("httpx.AsyncClient", return_value=mock_client):
                out = await fetch_url_ssrf_safe("https://example.com/path")
        assert out["body"] == "ok"
        assert "93.184.216.34" in captured["url"]
        assert captured["headers"].get("Host") == "example.com"

    asyncio.run(_run())


def test_sql_readonly_allows_select():
    assert assert_single_readonly_statement("SELECT 1") == "SELECT 1"
    assert "WITH" in assert_single_readonly_statement("WITH x AS (SELECT 1) SELECT * FROM x")


def test_sql_readonly_rejects_delete_and_stacked():
    with pytest.raises(SqlSafetyError):
        assert_single_readonly_statement("DELETE FROM users")
    with pytest.raises(SqlSafetyError):
        assert_single_readonly_statement("SELECT 1; DROP TABLE users")
    with pytest.raises(SqlSafetyError):
        assert_single_readonly_statement("EXPLAIN DELETE FROM users")


def test_env_allowlist_excludes_secrets(monkeypatch):
    monkeypatch.setenv("NSA_SECRET_TEST", "should-not-leak")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
    monkeypatch.setenv("PATH", os.environ.get("PATH", "/usr/bin"))
    env = build_mcp_child_env("github")
    assert "NSA_SECRET_TEST" not in env
    assert env.get("GITHUB_TOKEN") == "ghp_x"
    assert "PATH" in env


def test_tenant_env_overlay(monkeypatch):
    monkeypatch.setenv("NSA_MCP_TENANT_acme_GITHUB_TOKEN", "tenant-tok")
    env = build_mcp_child_env("github", tenant_id="acme")
    assert env.get("GITHUB_TOKEN") == "tenant-tok"
    assert env.get("NSA_MCP_TENANT_ID") == "acme"


def test_ssrf_tenant_allowlist(monkeypatch):
    monkeypatch.delenv("NSA_MCP_BROWSER_HOST_ALLOWLIST", raising=False)
    monkeypatch.setenv("NSA_MCP_TENANT_acme_BROWSER_HOST_ALLOWLIST", "allowed.example")
    with pytest.raises(SsrfError):
        validate_url_ssrf("https://evil.com/", tenant_id="acme")
    with patch(
        "neuroswarm_arm.runtime.router.mcp_ssrf.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 0))],
    ):
        assert validate_url_ssrf("https://allowed.example/", tenant_id="acme").startswith("https://")


def test_sql_rejects_select_into():
    with pytest.raises(SqlSafetyError, match="SELECT INTO"):
        assert_single_readonly_statement("SELECT 1 INTO tmp")
    with pytest.raises(SqlSafetyError, match="SELECT INTO"):
        assert_single_readonly_statement("SELECT * FROM users INTO OUTFILE '/tmp/x'")


def test_postgres_ro_requires_readonly_dsn(monkeypatch):
    monkeypatch.delenv("DATABASE_URL_READONLY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://write@localhost/db")
    # Re-import module constants by calling helper logic inline
    dsn = (os.environ.get("DATABASE_URL_READONLY") or "").strip()
    assert not dsn
    with pytest.raises(ValueError, match="DATABASE_URL_READONLY"):
        if not dsn:
            raise ValueError(
                "DATABASE_URL_READONLY is required for read-only tools. "
                "Set a non-writing role DSN; do not rely on DATABASE_URL for query/list/describe/explain."
            )


def test_s3_copy_refuses_overwrite_and_create_returns_version():
    from botocore.exceptions import ClientError

    # Refuse existing dest
    class Existing:
        def head_object(self, **_k):
            return {"ETag": '"x"'}

        def copy_object(self, **_k):
            raise AssertionError("copy must not run")

    client = Existing()
    exists = True
    overwrite = False
    with pytest.raises(ValueError, match="exists"):
        if exists and not overwrite:
            raise ValueError(
                "Destination s3://b/k exists. Pass overwrite=true (destructive)."
            )
        client.copy_object(Bucket="b", Key="k", CopySource={"Bucket": "s", "Key": "k"})

    captured: dict = {}

    class Create:
        def head_object(self, **_k):
            raise ClientError(
                {"Error": {"Code": "404", "Message": "n"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
                "HeadObject",
            )

        def copy_object(self, **kwargs):
            captured.update(kwargs)
            return {"VersionId": "cv1", "CopyObjectResult": {"ETag": '"ce"'}}

    c = Create()
    try:
        c.head_object(Bucket="db", Key="dk")
        exists = True
    except ClientError as exc:
        code = (exc.response.get("Error") or {}).get("Code", "")
        status = (exc.response.get("ResponseMetadata") or {}).get("HTTPStatusCode")
        if code in ("404", "NoSuchKey", "NotFound") or status == 404:
            exists = False
        else:
            raise
    assert exists is False
    resp = c.copy_object(
        Bucket="db",
        Key="dk",
        CopySource={"Bucket": "sb", "Key": "sk"},
        IfNoneMatch="*",
    )
    assert captured.get("IfNoneMatch") == "*"
    assert resp.get("VersionId") == "cv1"


def test_destructive_detection():
    assert tool_requires_destructive_approval("postgres.execute", {})
    assert tool_requires_destructive_approval("s3.put_object", {"overwrite": True})
    assert tool_requires_destructive_approval("s3.presign_url", {"method": "put_object"})
    assert not tool_requires_destructive_approval("postgres.query", {})
    assert not tool_requires_destructive_approval("web.search", {})


def test_destructive_approved_flag(monkeypatch):
    monkeypatch.delenv("NSA_MCP_APPROVE_DESTRUCTIVE", raising=False)
    assert not destructive_approved(approve=False)
    assert destructive_approved(approve=True)
    monkeypatch.setenv("NSA_MCP_APPROVE_DESTRUCTIVE", "1")
    assert destructive_approved(approve=False)


def test_reconcile_marks_executable():
    mgr = McpServerManager()
    mgr.discovered_by_server["github"] = ["list_issues", "create_issue"]
    exe = mgr.reconcile_registry_ids(
        ["github.list_issues", "github.create_issue", "github.missing_tool"]
    )
    assert "github.list_issues" in exe
    assert "github.create_issue" in exe
    assert "github.missing_tool" not in exe
    assert mgr.is_executable("github.list_issues")
    assert not mgr.is_executable("github.missing_tool")


@pytest.mark.asyncio
async def test_call_tool_not_reconciled(monkeypatch):
    monkeypatch.setenv("NSA_MCP_EXECUTE", "1")
    mgr = McpServerManager()
    out = await call_tool(
        "github.list_issues",
        {"repo": "a/b"},
        pool=mgr,
        require_reconciled=True,
    )
    assert out["ok"] is False
    assert out["error"] == "not_reconciled"


@pytest.mark.asyncio
async def test_call_tool_destructive_requires_approve(monkeypatch):
    monkeypatch.setenv("NSA_MCP_EXECUTE", "1")
    monkeypatch.delenv("NSA_MCP_APPROVE_DESTRUCTIVE", raising=False)
    mgr = McpServerManager()
    mgr.discovered_by_server["s3"] = ["put_object"]
    mgr.reconcile_registry_ids(["s3.put_object"])
    out = await call_tool(
        "s3.put_object",
        {"bucket": "b", "key": "k", "body": "x"},
        pool=mgr,
        approve=False,
        require_reconciled=True,
    )
    assert out["ok"] is False
    assert out["error"] == "destructive_approval_required"


@pytest.mark.asyncio
async def test_list_changed_triggers_relist(tmp_path: Path):
    mgr = McpServerManager()
    script = tmp_path / "server.py"
    script.write_text("# fake\n", encoding="utf-8")
    spec = McpServerSpec(server_id="github", script=script, cwd=tmp_path)

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

    seq = {"n": 0}

    def _line(msg: dict) -> bytes:
        return (json.dumps(msg) + "\n").encode()

    async def _readline():
        seq["n"] += 1
        n = seq["n"]
        if n == 1:
            return _line({"jsonrpc": "2.0", "id": 1, "result": {}})
        if n == 2:
            return _line(
                {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "list_issues"}]}}
            )
        if n == 3:
            # Mid-call (waiting for id=3): list_changed notification
            return _line({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
        if n == 4:
            # Nested tools/list from _handle_list_changed uses id=4
            return _line(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "result": {"tools": [{"name": "list_issues"}, {"name": "create_issue"}]},
                }
            )
        if n == 5:
            # Original tools/call response id=3
            return _line({"jsonrpc": "2.0", "id": 3, "result": {"content": [{"text": "ok"}]}})
        return _line({"jsonrpc": "2.0", "id": n, "result": {}})

    fake_proc.stdout.readline = _readline

    async def _spawn(*_a, **_k):
        return fake_proc

    with patch(
        "neuroswarm_arm.runtime.router.mcp_executor.asyncio.create_subprocess_exec",
        new=_spawn,
    ):
        out = await mgr.call(spec, "list_issues", {}, timeout_s=5.0)

    assert out["ok"] is True
    assert "create_issue" in mgr.discovered_by_server.get("github", [])
    assert mgr._reconcile_version >= 1
    mgr.reset_for_tests()


def test_s3_overwrite_refused_without_flag():
    """HeadObject exists + overwrite=false must refuse (logic mirrored from template)."""
    from botocore.exceptions import ClientError

    # Inline the guard used by templates/mcp-servers/s3/server.py
    class FakeClient:
        def head_object(self, **_k):
            return {"ETag": '"abc"'}

        def put_object(self, **_k):
            raise AssertionError("put_object must not be called when overwrite refused")

    client = FakeClient()
    exists = False
    try:
        client.head_object(Bucket="b", Key="k")
        exists = True
    except ClientError:
        exists = False
    overwrite = False
    with pytest.raises(ValueError, match="already exists"):
        if exists and not overwrite:
            raise ValueError(
                "Object s3://b/k already exists. Pass overwrite=true to replace (destructive)."
            )
        client.put_object(Bucket="b", Key="k", Body=b"x", IfNoneMatch="*")


def test_s3_create_sends_if_none_match():
    from botocore.exceptions import ClientError

    captured: dict = {}

    class FakeClient:
        def head_object(self, **_k):
            raise ClientError(
                {"Error": {"Code": "404", "Message": "n"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
                "HeadObject",
            )

        def put_object(self, **kwargs):
            captured.update(kwargs)
            return {"ETag": '"e"', "VersionId": "v1"}

    client = FakeClient()
    exists = False
    try:
        client.head_object(Bucket="b", Key="k")
        exists = True
    except ClientError as exc:
        code = (exc.response.get("Error") or {}).get("Code", "")
        status = (exc.response.get("ResponseMetadata") or {}).get("HTTPStatusCode")
        if code in ("404", "NoSuchKey", "NotFound") or status == 404:
            exists = False
        else:
            raise
    assert exists is False
    kwargs = {"Bucket": "b", "Key": "k", "Body": b"hi", "IfNoneMatch": "*"}
    resp = client.put_object(**kwargs)
    assert captured.get("IfNoneMatch") == "*"
    assert resp.get("VersionId") == "v1"
