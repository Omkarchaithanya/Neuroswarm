#!/usr/bin/env python3
"""Verify advertised *.tool.yaml IDs resolve to FastMCP function names.

Uses the same leaf + TOOL_NAME_ALIASES mapping as mcp_executor._mcp_tool_name.
Exit 0 only when every advertised registry ID has an exact executable contract.

With NSA_MCP_EXECUTE=1 and --live-list, also requires a successful tools/list
from each template server (protocol handshake).
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates" / "mcp-servers"

# Keep in sync with neuroswarm_arm.runtime.router.mcp_executor.TOOL_NAME_ALIASES
TOOL_NAME_ALIASES = {
    "send_message": "post_message",
    "open_page": "navigate",
    "list_objects_v2": "list_objects",
    "extract": "extract_links",
}

FAMILY_DIRS = {
    "browser": "browser",
    "github": "github",
    "postgres": "postgres",
    "s3": "s3",
    "slack": "slack",
    "web": "web-search",
    "web-search": "web-search",
}


def _yaml_id(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"(?m)^id:\s*[\"']?([^\s\"'#]+)", text)
    if m:
        return m.group(1).strip()
    family = path.parent.parent.name
    if family == "web-search":
        family = "web"
    return f"{family}.{path.stem.replace('.tool', '')}"


def _mcp_tool_name(tool_id: str) -> str:
    leaf = tool_id.split(".", 1)[-1] if "." in tool_id else tool_id
    return TOOL_NAME_ALIASES.get(leaf, leaf)


def _server_dir_for(tool_id: str) -> str:
    prefix = tool_id.split(".", 1)[0] if "." in tool_id else tool_id
    return FAMILY_DIRS.get(prefix, prefix)


def _fastmcp_names(server_py: Path) -> set[str]:
    """Parse @mcp.tool-decorated function names from server.py (no import)."""
    tree = ast.parse(server_py.read_text(encoding="utf-8"), filename=str(server_py))
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            call = dec
            if isinstance(dec, ast.Call):
                call = dec.func
            if isinstance(call, ast.Attribute) and call.attr == "tool":
                names.add(node.name)
                break
            if isinstance(call, ast.Name) and call.id == "tool":
                names.add(node.name)
                break
    return names


def _static_contract() -> int:
    yaml_files = sorted(TEMPLATES.rglob("*.tool.yaml"))
    if not yaml_files:
        print("FAIL: no *.tool.yaml under templates/mcp-servers")
        return 1

    advertised: list[str] = []
    for y in yaml_files:
        tid = _yaml_id(y)
        if tid:
            advertised.append(tid)

    implemented: set[str] = set()
    for server_py in sorted(TEMPLATES.glob("*/server.py")):
        for name in _fastmcp_names(server_py):
            implemented.add(name)

    exact = 0
    missing: list[tuple[str, str, str]] = []
    for tid in advertised:
        leaf = _mcp_tool_name(tid)
        sid = _server_dir_for(tid)
        server_py = TEMPLATES / sid / "server.py"
        names = _fastmcp_names(server_py) if server_py.exists() else set()
        if leaf in names:
            exact += 1
        else:
            missing.append((tid, leaf, sid))

    coverage = (exact / len(advertised) * 100.0) if advertised else 0.0
    print(f"Granular schemas advertised: {len(advertised)}")
    print(f"FastMCP functions implemented (all servers): {len(implemented)}")
    print(f"Exact registry-ID-to-function matches: {exact}")
    print(f"Advertised tools without exact executable contract: {len(missing)}")
    print(f"Exact execution-contract coverage: {coverage:.1f}%")
    if missing:
        print("\nMissing / mismatched:")
        for tid, leaf, sid in missing:
            print(f"  - {tid} → MCP name '{leaf}' not in {sid}/server.py")
        return 1
    print("mcp-execute-contract OK")
    return 0


async def _live_tools_list() -> int:
    sys.path.insert(0, str(ROOT))
    from neuroswarm_arm.runtime.router.mcp_executor import (
        McpServerManager,
        discover_template_servers,
    )

    mgr = McpServerManager()
    servers = discover_template_servers(TEMPLATES)
    if not servers:
        print("FAIL: no template servers for live tools/list")
        return 1
    failed: list[str] = []
    for sid, spec in servers.items():
        try:
            conn = await mgr.ensure(spec, timeout_s=45.0)
            names = [t.get("name") for t in conn.tools_list]
            print(f"  tools/list {sid}: {len(names)} tools hash={conn.catalog_hash}")
            if not names:
                failed.append(f"{sid}: empty tools/list")
        except Exception as exc:
            failed.append(f"{sid}: {exc}")
    await mgr.close_all()
    if failed:
        print("FAIL live tools/list:")
        for line in failed:
            print(f"  - {line}")
        return 1
    print("live tools/list OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-list",
        action="store_true",
        help="Spawn template servers and require tools/list (also: NSA_MCP_VERIFY_LIVE_LIST=1)",
    )
    args = parser.parse_args()
    rc = _static_contract()
    if rc != 0:
        return rc
    execute_on = os.getenv("NSA_MCP_EXECUTE", "") in {"1", "true", "True", "yes", "YES"}
    verify_live = args.live_list or os.getenv("NSA_MCP_VERIFY_LIVE_LIST", "") in {
        "1",
        "true",
        "True",
        "yes",
        "YES",
    }
    if execute_on and not verify_live:
        print(
            "Note: NSA_MCP_EXECUTE=1 — pass --live-list or NSA_MCP_VERIFY_LIVE_LIST=1 "
            "to require live tools/list"
        )
    if verify_live:
        print("Running live tools/list verification…")
        return asyncio.run(_live_tools_list())
    return 0


if __name__ == "__main__":
    sys.exit(main())
