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
    # Degraded when turbovec was requested but we are on numpy fallback.
    # Explicit exact/numpy backends are intentional → status ok.
    status = "ok"
    if ann_requested in {"turbovec", "turbo", "default"} and kernel == "numpy":
        status = "degraded"
    elif registry.size() < 0:
        status = "degraded"
    return {
        "status": status,
        "tools_registered": registry.size(),
        "index_size": index.size(),
        "ann_backend": getattr(index, "backend_name", "unknown"),
        "ann_backend_requested": ann_requested,
        "kernel_path": kernel,
        "sve_kernels_active": sve_kernels,
        "embedding_backend": embedder.backend_name,
        "embedding_dims": embedder.dims,
        "encoder": cfg.encoder_name,
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
