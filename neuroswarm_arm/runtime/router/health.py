"""Router health checks."""

from __future__ import annotations

from typing import Any

from .backends.registry import kernel_path_for


def build_health_report(runtime: Any) -> dict[str, Any]:
    cfg = runtime.config
    index = runtime.index
    embedder = runtime.embedder
    registry = runtime.registry
    feats = runtime.arm_features
    kernel = kernel_path_for(index)
    sve_kernels = bool(getattr(index, "sve_kernels_active", False))
    ann_requested = str(getattr(cfg, "ann_backend", "turbovec") or "turbovec").lower()
    min_tools = int(getattr(cfg, "turbovec_min_tools", 100) or 100)
    n_tools = int(registry.size())
    turbovec_import_ok = bool(getattr(index, "_turbovec_import_ok", False))
    # Degraded when turbovec was requested but import failed (forced numpy).
    # Below turbovec_min_tools with import OK → intentional exact → status ok.
    status = "ok"
    if ann_requested in {"turbovec", "turbo", "default"} and kernel == "numpy":
        if turbovec_import_ok and n_tools < min_tools:
            status = "ok"
        else:
            status = "degraded"
    return {
        "status": status,
        "tools_registered": n_tools,
        "index_size": index.size(),
        "ann_backend": getattr(index, "backend_name", "unknown"),
        "ann_backend_requested": ann_requested,
        "turbovec_min_tools": min_tools,
        "kernel_path": kernel,
        "sve_kernels_active": sve_kernels,
        "embedding_backend": embedder.backend_name,
        "embedding_dims": embedder.dims,
        "encoder": cfg.encoder_name,
        "embedding_backend_requested": getattr(cfg, "embedding_backend", "fastembed"),
        "top_k": cfg.top_k,
        "threshold": cfg.threshold,
        "high_conf_gate": getattr(cfg, "high_conf_gate", 0.85),
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
    }
