"""Per-server environment allowlists for MCP child processes."""

from __future__ import annotations

import os
import re
from typing import Any

# Minimal runtime vars always allowed (OS path lookup).
_BASE_RUNTIME = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "HOME",
    "USERPROFILE",
    "TMP",
    "TEMP",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "PLAYWRIGHT_BROWSERS_PATH",
    "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD",
)

_SERVER_ALLOW: dict[str, tuple[str, ...]] = {
    "github": ("GITHUB_TOKEN", "GITHUB_API"),
    "slack": ("SLACK_BOT_TOKEN",),
    "postgres": (
        "DATABASE_URL",
        "DATABASE_URL_READONLY",
        "NSA_MCP_PG_STATEMENT_TIMEOUT_MS",
        "NSA_MCP_PG_MAX_RESULT_BYTES",
    ),
    "s3": (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "S3_ENDPOINT_URL",
    ),
    "browser": (
        "NSA_MCP_BROWSER_HOST_ALLOWLIST",
        "NSA_MCP_BROWSER_MAX_REDIRECTS",
        "NSA_MCP_BROWSER_MAX_BYTES",
        "NSA_MCP_TENANT_ID",
    ),
    "web-search": ("BRAVE_API_KEY", "NSA_MCP_TENANT_ID", "NSA_MCP_BROWSER_HOST_ALLOWLIST"),
}


def build_mcp_child_env(
    server_id: str,
    *,
    tenant_id: str | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build a minimal env for an MCP child — never a full os.environ.copy()."""
    allowed = set(_BASE_RUNTIME)
    allowed.update(_SERVER_ALLOW.get(server_id, ()))
    # Prefix patterns for AWS / tenant overlays
    out: dict[str, str] = {}
    for key, val in os.environ.items():
        if key in allowed:
            out[key] = val
            continue
        if server_id == "s3" and key.startswith("AWS_"):
            out[key] = val
    if tenant_id:
        out["NSA_MCP_TENANT_ID"] = tenant_id
        prefix = f"NSA_MCP_TENANT_{tenant_id}_"
        prefix_u = prefix.upper()
        for key, val in os.environ.items():
            # Windows env keys are case-insensitive / often stored uppercased
            if not key.upper().startswith(prefix_u):
                continue
            short = key[len(prefix) :]
            if not short:
                continue
            out[short] = val
            for allowed_name in allowed:
                if allowed_name.upper() == short.upper():
                    out[allowed_name] = val
            # Map TENANT_*_BROWSER_HOST_ALLOWLIST → NSA_MCP_BROWSER_HOST_ALLOWLIST
            if short.upper() in {
                "BROWSER_HOST_ALLOWLIST",
                "NSA_MCP_BROWSER_HOST_ALLOWLIST",
            }:
                out["NSA_MCP_BROWSER_HOST_ALLOWLIST"] = val
    if extra:
        for k, v in extra.items():
            if k in allowed or (server_id == "s3" and k.startswith("AWS_")):
                out[k] = v
                continue
            # Tenant overlays may supply allowlisted short names only
            if tenant_id and k in allowed:
                out[k] = v
    # Ensure PYTHONPATH includes repo root so template servers can import neuroswarm_arm
    repo = os.environ.get("NSA_REPO_ROOT") or ""
    if not repo:
        # Best-effort: parent of templates
        try:
            from pathlib import Path

            here = Path(__file__).resolve().parents[3]
            repo = str(here)
        except Exception:
            repo = ""
    if repo:
        prev = out.get("PYTHONPATH", "")
        parts = [p for p in prev.split(os.pathsep) if p]
        if repo not in parts:
            parts.insert(0, repo)
        out["PYTHONPATH"] = os.pathsep.join(parts)
    return out


_DESTRUCTIVE_TOOLS = frozenset(
    {
        "execute",
        "insert_row",
        "create_index",
        "put_object",
        "copy_object",
        "delete_object",
        "create_issue",
        "upload_file",
        "set_topic",
        "add_reaction",
        "post_message",
        "send_message",
        "type_text",
        "click",
    }
)


def tool_requires_destructive_approval(tool_id: str, arguments: dict[str, Any] | None = None) -> bool:
    leaf = tool_id.split(".", 1)[-1] if "." in tool_id else tool_id
    if leaf in _DESTRUCTIVE_TOOLS:
        return True
    args = arguments or {}
    if leaf == "presign_url" and str(args.get("method", "")).lower() == "put_object":
        return True
    if leaf in {"put_object", "copy_object"} and args.get("overwrite") is True:
        return True
    return False


def destructive_approved(*, approve: bool | None = None) -> bool:
    if approve is True:
        return True
    raw = os.getenv("NSA_MCP_APPROVE_DESTRUCTIVE", "")
    return raw in {"1", "true", "True", "yes", "YES"}
