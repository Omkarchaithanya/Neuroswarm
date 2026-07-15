"""Router health checks."""

from __future__ import annotations

from typing import Any


def build_health_report(runtime: Any) -> dict[str, Any]:
    cfg = runtime.config
    index = runtime.index
    embedder = runtime.embedder
    registry = runtime.registry
    feats = runtime.arm_features
    return {
        "status": "ok" if registry.size() >= 0 else "degraded",
        "tools_registered": registry.size(),
        "index_size": index.size(),
        "ann_backend": getattr(index, "backend_name", "unknown"),
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
            "sve2": feats.sve2,
            "numa_nodes": feats.numa_nodes,
        },
        "hot_reload": cfg.enable_hot_reload,
        "snapshot_dir": str(cfg.snapshot_dir),
    }
