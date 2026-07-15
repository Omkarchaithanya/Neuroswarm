"""DI factory for MAKS Memory OS (Layer 5)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .backends import build_default_backends
from .capability import build_default_capability_registry
from .compression import build_compression
from .config import MAKSConfig, load_maks_config
from .manager import ConfigARMORAPolicy, KVManager
from .metrics import MAKSMetrics
from .pool import GlobalPagePool
from .registry import KVRegistry
from .storage import RedisRegistryStore, SQLiteRegistryStore

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.kv.manager.runtime import KVRuntimeManager


def build_registry_store(cfg: MAKSConfig):
    backend = (cfg.registry_backend or "sqlite").lower()
    if backend == "redis":
        store = RedisRegistryStore(cfg.redis_url)
        if store.available:
            return store
        # Fall back to sqlite on Axion when Redis down
    if backend in {"memory", "mem", "none"}:
        return None
    path = cfg.root / "maks" / "registry" / "registry.sqlite"
    return SQLiteRegistryStore(path)


def build_maks(
    cfg: MAKSConfig | None = None,
    *,
    root: Path | None = None,
    kv_runtime: KVRuntimeManager | None = None,
    metrics_bridge: object | None = None,
    enable_scheduler: bool | None = None,
    armora: object | None = None,
) -> KVManager:
    """Construct Layer-5 MAKS Memory OS (no global state).

    ``kv_runtime`` is retained as Plane-2 compatibility facade; pressure is owned by MAKS.
    ``armora`` should implement IARMORAPolicy (prefer neuroswarm_arm.armora.ArmoraBudgetPolicy).
    """
    config = cfg or load_maks_config(root)
    if root is not None and cfg is None:
        config = load_maks_config(root)

    store = build_registry_store(config)
    registry = KVRegistry(store)
    providers = build_default_backends(config)
    compression = build_compression(config.compression)
    metrics = MAKSMetrics(bridge=metrics_bridge)
    capabilities = build_default_capability_registry()
    pool = GlobalPagePool(page_bytes=getattr(config, "page_bytes", 64 * 1024))
    if armora is None:
        try:
            from neuroswarm_arm.armora import ArmoraBudgetPolicy, BudgetConfig

            armora = ArmoraBudgetPolicy(
                BudgetConfig(
                    max_cost_usd=float(getattr(config, "max_cost", 0.05) or 0.05),
                    max_memory_bytes=int(
                        getattr(config, "max_memory_bytes", 0)
                        or getattr(config, "ram_budget_bytes", 8 * 1024**3)
                        or 8 * 1024**3
                    ),
                    max_cache_entries=int(
                        getattr(config, "max_cache_entries", 10_000) or 10_000
                    ),
                    max_ttl_s=float(getattr(config, "default_ttl_s", 3600.0) or 3600.0),
                )
            )
        except Exception:
            armora = ConfigARMORAPolicy(config)

    manager = KVManager(
        config,
        registry,
        providers,
        metrics=metrics,
        armora=armora,  # type: ignore[arg-type]
        compression=compression,
        enable_scheduler=enable_scheduler,
        capabilities=capabilities,
        pool=pool,
    )

    # Bind Plane-2 facade → MAKS pressure (absorb path)
    if kv_runtime is not None:
        try:
            from neuroswarm_arm.runtime.kv.facade import bind_maks_pressure

            bind_maks_pressure(kv_runtime, manager)
        except Exception:
            pass
        try:
            metrics.set(
                "maks_provider_usage_bytes",
                float(manager.allocator.used_bytes),
            )
        except Exception:
            pass

    if enable_scheduler is None:
        enable_scheduler = config.enable_scheduler
    if enable_scheduler:
        manager.start()
    return manager
