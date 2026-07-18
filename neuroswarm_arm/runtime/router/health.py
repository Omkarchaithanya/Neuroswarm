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
    return {
        "status": "ok" if registry.size() >= 0 else "degraded",
        "tools_registered": registry.size(),
        "index_size": index.size(),
        "ann_backend": getattr(index, "backend_name", "unknown"),
        "kernel_path": kernel,
        "sve_kernels_active": sve_kernels,
        "embedding_backend": embedder.backend_name,
        "embedding_dims": embedder.dims,
        "encoder": cfg.encoder_name,
        "top_k": cfg.top_k,
        "threshold": cfg.threshold,
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
