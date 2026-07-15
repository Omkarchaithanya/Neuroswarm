"""KVRuntimeManager — central Plane-2 controller."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..block.models import Block, SessionBlockTable
from ..checkpoint import CheckpointEngine, FileCheckpointStore
from ..interfaces.types import PressureSnapshot, StorageTier
from ..manager.block_manager import AllocateRequest, KVBlockManager
from ..manager.prefix import PrefixMatchResult
from ..migration import KVTieringEngine
from ..providers.registry import ProviderRegistry
from ..recovery import RecoveryEngine
from ..scheduler import MigrationScheduler
from ..security import AccessPolicy
from ..sharing.engine import SharedKVEngine
from ..telemetry import KVTelemetry
from ..utils.config import KVRuntimeConfig
from ..utils.hashing import content_hash
from ..utils.logging import get_logger

logger = get_logger("neuroswarm.kv.runtime")


@dataclass
class KVRuntimeManager:
    """Sole public controller for allocate/release/migrate/checkpoint/share/telemetry."""

    config: KVRuntimeConfig
    providers: ProviderRegistry
    block_manager: KVBlockManager
    tiering: KVTieringEngine
    scheduler: MigrationScheduler
    sharing: SharedKVEngine
    checkpoint_engine: CheckpointEngine
    recovery: RecoveryEngine
    telemetry: KVTelemetry
    security: AccessPolicy = field(default_factory=AccessPolicy)

    def create_session(self, session_id: str, *, agent_id: str = "") -> SessionBlockTable:
        return self.block_manager.create_session(session_id, agent_id=agent_id)

    def get_session(self, session_id: str) -> SessionBlockTable | None:
        return self.block_manager.get_session(session_id)

    async def allocate(
        self,
        session_id: str,
        payload: bytes,
        *,
        layer: int = 0,
        head: int = 0,
        token_start: int = 0,
        token_end: int = 0,
        priority: int = 0,
        agent_id: str = "",
        prefix_hash: str = "",
    ) -> Block:
        # Automatic prefix reuse when allocating sequential blocks
        block = await self.block_manager.allocate(
            AllocateRequest(
                session_id=session_id,
                payload=payload,
                layer=layer,
                head=head,
                token_start=token_start,
                token_end=token_end,
                priority=priority,
                agent_id=agent_id,
                prefix_hash=prefix_hash,
            )
        )
        self._refresh_gauges()
        if self.tiering.should_migrate():
            self.scheduler.enqueue(
                block.physical_id or "",
                StorageTier.L2_COMPRESSED_RAM,
                priority=0,
            )
        return block

    async def release(self, session_id: str) -> None:
        await self.block_manager.release_session(session_id)
        self._refresh_gauges()

    async def migrate(self, physical_id: str, target_tier: StorageTier) -> bool:
        ok = await self.tiering.migrate_block(physical_id, target_tier)
        if ok:
            self.telemetry.inc("kv_migration_count")
        self._refresh_gauges()
        return ok

    def lookup_prefix(self, block_payloads: list[bytes]) -> PrefixMatchResult:
        match = self.block_manager.lookup_prefix(block_payloads)
        if match.hit:
            self.telemetry.inc("kv_prefix_hits")
        else:
            self.telemetry.inc("kv_prefix_misses")
        self.telemetry.set("kv_hit_rate", self.block_manager.prefix_cache.hit_rate)
        self.telemetry.set("kv_miss_rate", self.block_manager.prefix_cache.miss_rate)
        return match

    def reuse_prefix(
        self,
        session_id: str,
        match: PrefixMatchResult,
        *,
        agent_id: str = "",
    ) -> list[Block]:
        blocks = self.block_manager.reuse_prefix(session_id, match, agent_id=agent_id)
        self._refresh_gauges()
        return blocks

    async def share(
        self,
        physical_id: str,
        consumer_id: str,
        *,
        session_id: str = "",
        token: str | None = None,
    ) -> str:
        if token and session_id and not self.security.authorize(token, session_id, share=True):
            raise PermissionError("share not authorized")
        data = await self.block_manager.read_payload(physical_id)
        await self.sharing.store(physical_id, data)
        share_token = await self.sharing.share(physical_id, consumer_id)
        self.telemetry.set(
            "kv_blocks_shared",
            float(self.block_manager.physical.shared_count()),
        )
        return share_token

    async def deduplicate(self, session_id: str, payload: bytes) -> Block:
        """Allocate with dedup (identical payloads share one physical block)."""
        return await self.allocate(session_id, payload)

    async def checkpoint(self, session_id: str) -> dict[str, Any]:
        start = time.monotonic()
        session = self.block_manager.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        logical = self.block_manager.logical_tables[session_id]
        payloads: dict[str, bytes] = {}
        content_hashes: dict[str, str] = {}
        physical_records = []
        for block in session.blocks.values():
            pid = block.physical_id
            if not pid:
                continue
            data = await self.block_manager.read_payload(pid)
            payloads[pid] = data
            content_hashes[pid] = content_hash(data)
            rec = self.block_manager.physical.get(pid)
            if rec is not None:
                physical_records.append(rec.to_dict())
        meta = {
            "session": session.to_dict(),
            "logical_map": logical.to_dict(),
            "physical_records": physical_records,
            "payload_ids": list(payloads.keys()),
            "content_hashes": content_hashes,
            "checkpointed_at": time.time(),
        }
        result = await self.checkpoint_engine.checkpoint(session_id, meta, payloads)
        self.recovery.write_journal(session_id, {"event": "checkpoint", "blocks": len(payloads)})
        latency = (time.monotonic() - start) * 1000.0
        self.telemetry.observe("kv_checkpoint_latency", latency)
        for block in session.blocks.values():
            block.status = block.status  # noqa: intentional no-op keep status
        return {**result, "latency_ms": latency}

    async def restore(self, session_id: str) -> SessionBlockTable:
        start = time.monotonic()
        meta, payloads = await self.checkpoint_engine.restore(session_id)
        result = self.recovery.recover_from_checkpoint(
            session_id,
            meta,
            payloads,
            physical=self.block_manager.physical,
        )
        if not result.ok:
            raise ValueError(f"corrupt checkpoint for session {session_id}")
        session, logical = self.recovery.rebuild_tables(
            meta, physical=self.block_manager.physical
        )
        # Rehydrate payloads into L1
        provider = self.providers.for_tier(StorageTier.L1_RAM)
        for pid, data in payloads.items():
            rec = self.block_manager.physical.get(pid)
            key = rec.provider_key if rec else pid
            await provider.put(key, data)
            if rec is not None:
                self.block_manager.physical.update_tier(pid, StorageTier.L1_RAM, key)
        self.block_manager.sessions[session_id] = session
        self.block_manager.logical_tables[session_id] = logical
        latency = (time.monotonic() - start) * 1000.0
        self.telemetry.observe("kv_restore_latency", latency)
        self._refresh_gauges()
        return session

    async def resume(self, session_id: str) -> SessionBlockTable:
        existing = self.block_manager.get_session(session_id)
        if existing is not None:
            return existing
        return await self.restore(session_id)

    def metrics(self) -> dict[str, float]:
        self._refresh_gauges()
        return self.telemetry.snapshot()

    def pressure_snapshot(self) -> PressureSnapshot:
        self._refresh_gauges()
        snap = self.telemetry.snapshot()
        return PressureSnapshot(
            pressure=self.tiering.memory_pressure(),
            hit_rate=snap.get("kv_hit_rate", 0.0),
            miss_rate=snap.get("kv_miss_rate", 0.0),
            ram_usage_bytes=int(snap.get("kv_ram_usage", 0.0)),
            storage_usage_bytes=int(snap.get("kv_storage_usage", 0.0)),
            blocks_total=int(snap.get("kv_blocks_total", 0.0)),
            blocks_shared=int(snap.get("kv_blocks_shared", 0.0)),
            migration_latency_ms=self.tiering.last_migration_latency_ms,
            dominant_tier=self.tiering.dominant_tier(),
            fragmentation=self.tiering.fragmentation(),
        )

    def hot_block_ids(self, limit: int = 32) -> list[str]:
        records = sorted(
            self.block_manager.physical.all_records(),
            key=lambda r: (r.access_count, r.last_access),
            reverse=True,
        )
        return [r.physical_id for r in records[:limit]]

    def status(self) -> dict[str, Any]:
        pressure = self.pressure_snapshot()
        return {
            "ok": True,
            "sessions": len(self.block_manager.sessions),
            "blocks": len(self.block_manager.physical),
            "providers": self.providers.list_providers(),
            "sharing_backend": self.sharing.name,
            "scheduler_pending": self.scheduler.pending,
            "pressure": pressure.to_dict(),
            "block_size_tokens": self.config.block_size_tokens,
            "numa_node": self.block_manager.numa_policy.preferred,
            "numa_multi_node": self.block_manager.numa_policy.multi_node,
        }

    def _refresh_gauges(self) -> None:
        physical = self.block_manager.physical
        records = physical.all_records()
        self.telemetry.set("kv_blocks_total", float(len(records)))
        self.telemetry.set("kv_blocks_shared", float(physical.shared_count()))
        self.telemetry.set(
            "kv_reference_count",
            float(sum(r.refcount for r in records)),
        )
        self.telemetry.set("kv_ram_usage", float(self.providers.ram_usage()))
        self.telemetry.set("kv_storage_usage", float(self.providers.storage_usage()))
        self.telemetry.set("kv_dedup_ratio", float(self.block_manager.dedup.dedup_ratio))
        self.telemetry.set("kv_reuse_ratio", float(self.block_manager.prefix_cache.hit_rate))
        self.telemetry.set("kv_hit_rate", float(self.block_manager.prefix_cache.hit_rate))
        self.telemetry.set("kv_miss_rate", float(self.block_manager.prefix_cache.miss_rate))
        self.telemetry.set("kv_fragmentation", float(self.tiering.fragmentation()))
        self.telemetry.set("kv_migration_count", float(self.tiering.migrations))
        self.telemetry.set("kv_evictions", float(self.tiering.evictions))
        # Compression ratio from L2 if available
        try:
            l2 = self.providers.get_tier(StorageTier.L2_COMPRESSED_RAM)
            if l2 is not None:
                ratio = getattr(l2, "compression_ratio", lambda: 1.0)()
                self.telemetry.set("kv_compression_ratio", float(ratio))
            else:
                self.telemetry.set("kv_compression_ratio", 1.0)
        except Exception:
            self.telemetry.set("kv_compression_ratio", 1.0)

    def shutdown(self) -> None:
        self.scheduler.stop()
        logger.info("kv_runtime_shutdown")
