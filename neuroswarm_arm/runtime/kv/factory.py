"""DI factory for the KV Memory Runtime."""

from __future__ import annotations

from pathlib import Path

from .allocator.numa import LocalRAMAllocator, NUMAPlacementPolicy
from .block.tables import PhysicalBlockTable
from .checkpoint import CheckpointEngine, FileCheckpointStore
from .compression import build_compression
from .manager.block_manager import KVBlockManager
from .manager.runtime import KVRuntimeManager
from .migration import KVTieringEngine, TieringPolicy
from .providers.registry import build_default_providers
from .recovery import RecoveryEngine
from .scheduler import MigrationScheduler
from .sharing.engine import SharedKVEngine, build_sharing_backend
from .telemetry import KVTelemetry
from .utils.config import KVRuntimeConfig, load_kv_config


def build_kv_runtime(
    cfg: KVRuntimeConfig | None = None,
    *,
    root: Path | None = None,
    metrics_bridge: object | None = None,
    enable_background: bool | None = None,
) -> KVRuntimeManager:
    """Construct a fully wired KVRuntimeManager (zero global state)."""
    config = cfg or load_kv_config(root)
    if root is not None and cfg is None:
        config = load_kv_config(root)

    compression = build_compression(config.compression)
    providers = build_default_providers(config, compression)
    physical = PhysicalBlockTable()
    numa = NUMAPlacementPolicy(preferred_node=config.numa_preferred_node)
    allocator = LocalRAMAllocator(
        node_id=numa.choose_node(),
        budget_bytes=config.ram_budget_bytes,
    )
    block_manager = KVBlockManager(
        providers=providers,
        physical=physical,
        numa_policy=numa,
        allocator=allocator,
        block_size_tokens=config.block_size_tokens,
    )
    tiering = KVTieringEngine(
        providers=providers,
        physical=physical,
        policy=TieringPolicy(pressure_threshold=config.pressure_threshold),
        ram_budget_bytes=config.ram_budget_bytes,
    )
    bg = config.enable_background_migration if enable_background is None else enable_background
    scheduler = MigrationScheduler(
        tiering,
        interval_s=config.migration_interval_s,
        enable_background=bg,
    )
    sharing = SharedKVEngine(build_sharing_backend(config))
    assert config.checkpoint_dir is not None
    checkpoint = CheckpointEngine(FileCheckpointStore(config.checkpoint_dir))
    recovery = RecoveryEngine(config.root / "journal")
    telemetry = KVTelemetry(bridge=metrics_bridge)

    # Register metric descriptions on the global bridge if present
    if metrics_bridge is not None and hasattr(metrics_bridge, "describe"):
        for name, mtype in telemetry.types.items():
            metrics_bridge.describe(name, mtype, telemetry.help_text.get(name, ""))

    return KVRuntimeManager(
        config=config,
        providers=providers,
        block_manager=block_manager,
        tiering=tiering,
        scheduler=scheduler,
        sharing=sharing,
        checkpoint_engine=checkpoint,
        recovery=recovery,
        telemetry=telemetry,
    )
