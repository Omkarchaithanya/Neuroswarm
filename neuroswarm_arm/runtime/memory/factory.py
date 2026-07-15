"""Factory / DI — Mem0 primary; JSON emergency-only."""

from __future__ import annotations

from pathlib import Path

from neuroswarm_arm.runtime.memory.adapter import Mem0Adapter
from neuroswarm_arm.runtime.memory.adapter.sdk_client import Mem0SdkClient
from neuroswarm_arm.runtime.memory.api import NeuroMemory
from neuroswarm_arm.runtime.memory.config import MemoryRuntimeConfig, load_memory_config
from neuroswarm_arm.runtime.memory.logging import log_event
from neuroswarm_arm.runtime.memory.providers.json_fallback import JsonFallbackProvider
from neuroswarm_arm.runtime.memory.service import MemoryRuntime


def build_provider(cfg: MemoryRuntimeConfig):
    """Return (primary IMemoryProvider, emergency_json | None)."""
    emergency = JsonFallbackProvider(cfg.store_root / "json")
    # Explicit json only for tests / forced offline
    if cfg.provider in {"json", "fallback", "emergency"}:
        log_event("provider_selected", provider="json_emergency_forced")
        return emergency, None

    # Default and mem0/auto: try official Mem0 first
    try:
        from neuroswarm_arm.runtime.memory.mem0.provider import Mem0Provider

        primary = Mem0Provider(cfg)
        log_event("provider_selected", provider="mem0")
        return primary, emergency
    except Exception as exc:  # noqa: BLE001
        log_event("provider_emergency_fallback", reason=str(exc))
        return emergency, None


def build_mem0_adapter(
    store_root: Path | str | None = None,
    *,
    config: MemoryRuntimeConfig | None = None,
) -> Mem0Adapter:
    cfg = config or load_memory_config(Path(store_root) if store_root else None)
    emergency = JsonFallbackProvider(cfg.store_root / "json")
    if cfg.provider in {"json", "fallback", "emergency"}:
        client = Mem0SdkClient(cfg, disabled=True)
        adapter = Mem0Adapter(cfg, client=client, emergency=emergency)
        adapter._use_emergency = True
        log_event("adapter_emergency", reason="json_provider_forced")
        return adapter
    adapter = Mem0Adapter(cfg, emergency=emergency)
    if not adapter.client.available:
        adapter._use_emergency = True
        log_event("adapter_emergency", reason="mem0_unavailable")
    return adapter


def build_memory_runtime(
    store_root: Path | str | None = None,
    *,
    config: MemoryRuntimeConfig | None = None,
) -> NeuroMemory:
    cfg = config or load_memory_config(Path(store_root) if store_root else None)
    primary, fallback = build_provider(cfg)
    runtime = MemoryRuntime(primary, cfg, fallback=fallback)
    if cfg.provider in {"json", "fallback", "emergency"}:
        adapter = build_mem0_adapter(config=cfg)
        return NeuroMemory(runtime, adapter=adapter)
    adapter = build_mem0_adapter(config=cfg)
    return NeuroMemory(runtime, adapter=adapter)
