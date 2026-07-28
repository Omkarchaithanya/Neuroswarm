"""Router health checks."""

from __future__ import annotations

from typing import Any

from .backends.registry import kernel_path_for


def _active_backend_for(index: Any, *, ann_requested: str, kernel: str) -> str:
    """Honest active search path — never use ambiguous turbovec+exact as active."""
    if hasattr(index, "active_backend"):
        return str(index.active_backend)
    if kernel == "turbovec":
        return "turbovec"
    name = str(getattr(index, "backend_name", "") or "").lower()
    if name in {"exact", "numpy"} or ann_requested in {"exact", "numpy", "brute"}:
        return "exact_numpy"
    if "turbovec" in name and kernel == "numpy":
        return "exact_numpy"
    if kernel == "numpy":
        return "exact_numpy"
    return name or "unknown"


def _fallback_reason_for(
    index: Any,
    *,
    ann_requested: str,
    active: str,
    n_tools: int,
    min_tools: int,
    turbovec_import_ok: bool,
) -> str:
    if hasattr(index, "fallback_reason") and ann_requested in {"turbovec", "turbo", "default"}:
        return str(index.fallback_reason)
    if active == "turbovec" or (active.startswith("turbovec") and active != "turbovec+exact"):
        return "none"
    if ann_requested in {"exact", "numpy", "brute"}:
        return "forced_exact"
    if ann_requested in {"turbovec", "turbo", "default"}:
        if not turbovec_import_ok:
            return "import_failed"
        if n_tools < min_tools:
            return "catalog_below_min_tools"
        return "runtime_fallback"
    return "none"


def build_health_report(runtime: Any) -> dict[str, Any]:
    cfg = runtime.config
    index = runtime.index
    embedder = runtime.embedder
    registry = runtime.registry
    feats = runtime.arm_features
    kernel = kernel_path_for(index)
    sve_kernels = bool(getattr(index, "sve_kernels_active", False))
    ann_requested = str(getattr(cfg, "ann_backend", "turbovec") or "turbovec").lower()
    min_tools = int(getattr(cfg, "turbovec_min_tools", 0) or 0)
    n_tools = int(registry.size())
    turbovec_import_ok = bool(getattr(index, "_turbovec_import_ok", False))
    active = _active_backend_for(index, ann_requested=ann_requested, kernel=kernel)
    fallback_reason = _fallback_reason_for(
        index,
        ann_requested=ann_requested,
        active=active,
        n_tools=n_tools,
        min_tools=min_tools,
        turbovec_import_ok=turbovec_import_ok,
    )
    # Degraded when turbovec was requested but import failed (forced numpy).
    # Below turbovec_min_tools with import OK → intentional exact → status ok.
    status = "ok"
    if ann_requested in {"turbovec", "turbo", "default"} and kernel == "numpy":
        if turbovec_import_ok and n_tools < min_tools:
            status = "ok"
        else:
            status = "degraded"
    mcp_block = _mcp_manager_status()
    if mcp_block.get("execute_enabled") and int(mcp_block.get("executable_count") or 0) == 0:
        status = "degraded"
    tools_list = registry.as_list() if hasattr(registry, "as_list") else []
    return {
        "status": status,
        "tools_registered": n_tools,
        "catalog_size": n_tools,
        "index_size": index.size(),
        "ann_backend": getattr(index, "backend_name", "unknown"),
        "ann_backend_requested": ann_requested,
        "configured_backend": ann_requested,
        "active_backend": active,
        "fallback_reason": fallback_reason,
        "turbovec_min_tools": min_tools,
        "kernel_path": kernel,
        "sve_kernels_active": sve_kernels,
        "embedding_backend": embedder.backend_name,
        "embedding_dims": embedder.dims,
        "encoder": cfg.encoder_name,
        "embedding_backend_requested": getattr(cfg, "embedding_backend", "fastembed"),
        "top_k": cfg.top_k,
        "threshold": cfg.threshold,
        "high_conf_gate": getattr(cfg, "high_conf_gate", 0.70),
        "cache": embedder.cache.stats() if embedder.cache else {},
        "arm": {
            "arch": feats.arch,
            "is_arm64": feats.is_arm64,
            "neon": feats.neon,
            "sve": getattr(feats, "sve", False),
            "sve2": feats.sve2,
            "numa_nodes": feats.numa_nodes,
        },
        "hot_reload": cfg.enable_hot_reload,
        "snapshot_dir": str(cfg.snapshot_dir),
        "tools_advertised": n_tools,
        "tools_executable": sum(
            1 for t in tools_list if getattr(t, "executable", False)
        ),
        "mcp": mcp_block,
        "memory": _memory_status(runtime),
        "history_ranker_degraded": bool(
            getattr(getattr(runtime, "history", None), "history_ranker_degraded", False)
        ),
    }


def _memory_status(runtime: Any) -> dict[str, Any]:
    history = getattr(runtime, "history", None)
    if history is not None and hasattr(history, "status"):
        try:
            return history.status()
        except Exception as exc:
            return {"error": str(exc), "emergency_active": True, "history_ranker_degraded": True}
    return {"provider": "unknown", "emergency_active": False, "history_ranker_degraded": False}


def _mcp_manager_status() -> dict[str, Any]:
    try:
        from .mcp_executor import get_mcp_manager, mcp_execute_enabled

        mgr = get_mcp_manager()
        st = mgr.status()
        st["execute_enabled"] = mcp_execute_enabled()
        return st
    except Exception as exc:
        return {"error": str(exc)}
