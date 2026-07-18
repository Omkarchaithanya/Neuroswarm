"""HTTP JSON-RPC bridge for Arm Performix — live Axion path for AROP MCP.

Implements the surface ``PerformixMCPClient`` already calls (``POST /mcp``).
Runs host ``apx`` via ``PerformixClient`` (timeout + export), not a fake Arm MCP port.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from neuroswarm_arm.evolution.performix_client import PerformixClient

LOG = logging.getLogger("nexus.performix.bridge")

TOOLS = [
    {"name": "apx_recipe_run", "description": "Run an Arm Performix recipe via apx"},
    {"name": "apx_recipe_compare", "description": "Compare two Performix recipe outputs"},
    {
        "name": "kb_search",
        "description": "Unavailable on performix-bridge (not wired; use host apx/KB separately)",
        "available": False,
    },
]


def create_app(
    *,
    binary: str | None = None,
    snapshot_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="performix-bridge", version="0.1.0")
    client = PerformixClient(binary=binary or os.getenv("NSA_AROP_PERFORMIX_BIN", "apx"))
    out_root = Path(
        snapshot_dir
        or os.getenv("NSA_AROP_PERFORMIX_BRIDGE_OUT", "work/performix/bridge")
    )
    out_root.mkdir(parents=True, exist_ok=True)
    snap = Path(os.getenv("NSA_RMF_PERFORMIX_PATH", "work/performix/snapshot.json"))

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "binary": client.binary,
            "snapshot": str(snap),
            "tools": [t["name"] for t in TOOLS],
        }

    @app.post("/mcp")
    async def mcp(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

        method = str(body.get("method") or "")
        params = body.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        req_id = body.get("id", 1)

        try:
            if method in {"tools/list", "list_tools"}:
                result: Any = {"tools": TOOLS}
            elif method in {"tools/call", "call_tool"}:
                result = _call_tool(client, params, out_root=out_root, snap=snap)
            else:
                result = {"ok": False, "error": f"unknown_method:{method}"}
            # Flatten result for PerformixMCPClient (reads tools/ok at top level).
            payload: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "result": result}
            if isinstance(result, dict):
                payload.update(result)
            return JSONResponse(payload)
        except Exception as exc:
            LOG.exception("mcp call failed")
            return JSONResponse(
                {"jsonrpc": "2.0", "id": req_id, "ok": False, "error": str(exc)},
                status_code=500,
            )

    return app


def _call_tool(
    client: PerformixClient,
    params: dict[str, Any],
    *,
    out_root: Path,
    snap: Path,
) -> dict[str, Any]:
    name = str(params.get("name") or "")
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        args = {}

    if name == "apx_recipe_run":
        recipe = str(args.get("recipe") or "code_hotspots")
        duration = args.get("duration") or args.get("timeout")
        target = args.get("target") or os.getenv("ARM_PERFORMIX_TARGET") or None
        out_arg = args.get("output")
        output = Path(out_arg) if out_arg else (out_root / f"{recipe}.json")
        payload = client.run_recipe(
            recipe,
            output,
            target=str(target) if target else None,
            duration=int(duration) if duration is not None else None,
        )
        ok = int(payload.get("returncode", 1)) == 0
        refreshed = False
        if ok and output.exists():
            try:
                snap.parent.mkdir(parents=True, exist_ok=True)
                snap.write_bytes(output.read_bytes())
                refreshed = True
            except Exception as exc:
                LOG.warning("failed to refresh snapshot %s: %s", snap, exc)
        elif not ok:
            # Honest marker — never leave a prior demo snapshot claiming live data.
            _mark_snapshot_unavailable(snap, error="apx_recipe_failed")
        return {
            "ok": ok,
            "tool": name,
            "snapshot_refreshed": refreshed,
            "parsed": payload,
            "texts": [json.dumps(payload)[:8000]],
            "output": str(output),
        }

    if name == "apx_recipe_compare":
        baseline = Path(str(args.get("baseline") or ""))
        optimized = Path(str(args.get("optimized") or ""))
        output = Path(str(args.get("output") or (out_root / "compare.json")))
        payload = client.compare(baseline, optimized, output)
        return {
            "ok": int(payload.get("returncode", 1)) == 0,
            "tool": name,
            "parsed": payload,
            "texts": [json.dumps(payload)[:8000]],
        }

    if name == "kb_search":
        return {
            "ok": False,
            "tool": name,
            "available": False,
            "parsed": {"hits": [], "note": "kb_search not available on performix-bridge"},
            "texts": ["kb_search unavailable"],
            "error": "kb_search_unavailable",
        }

    return {"ok": False, "error": f"unknown_tool:{name}"}


def _mark_snapshot_unavailable(snap: Path, *, error: str = "apx_recipe_failed") -> None:
    """Replace demo/synthetic snapshot with an honest unavailable marker."""
    try:
        if snap.is_file():
            try:
                src = str(json.loads(snap.read_text(encoding="utf-8")).get("source") or "")
            except Exception:
                src = "demo"
            if src not in {"demo", "synthetic", "unavailable", ""}:
                # Keep a prior live apx snapshot; only clear soft-fail demos.
                if src == "apx":
                    return
        snap.parent.mkdir(parents=True, exist_ok=True)
        marker = {
            "available": 0,
            "source": "unavailable",
            "error": error,
            "hotspots": [],
            "ipc": 0.0,
            "pmu_available": 0.0,
        }
        snap.write_text(json.dumps(marker, indent=2), encoding="utf-8")
        LOG.info("snapshot marked unavailable at %s (%s)", snap, error)
    except Exception as exc:
        LOG.warning("failed to mark snapshot unavailable: %s", exc)


def main() -> None:
    import uvicorn

    host = os.getenv("NSA_PERFORMIX_BRIDGE_HOST", "0.0.0.0")
    port = int(os.getenv("NSA_PERFORMIX_BRIDGE_PORT", "8090"))
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
