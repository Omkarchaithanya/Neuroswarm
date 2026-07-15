"""KV tiering / migration policy engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..block.tables import PhysicalBlockTable
from ..interfaces.migrator import IKVMigrator
from ..interfaces.types import BlockTemperature, PhysicalBlockRecord, StorageTier
from ..providers.registry import ProviderRegistry
from ..utils.logging import get_logger

logger = get_logger("neuroswarm.kv.tiering")

TIER_ORDER = [
    StorageTier.L1_RAM,
    StorageTier.L2_COMPRESSED_RAM,
    StorageTier.L3_MEMORY_MAPPED,
    StorageTier.L3_NVME,
    StorageTier.L4_LMDB,
    StorageTier.L5_REDIS,
]


@dataclass
class TieringPolicy:
    pressure_threshold: float = 0.70
    hot_access_window_s: float = 60.0
    warm_access_window_s: float = 600.0
    cold_min_refcount: int = 1

    def temperature(self, rec: PhysicalBlockRecord, now: float | None = None) -> BlockTemperature:
        now = time.time() if now is None else now
        age = now - rec.last_access
        if age <= self.hot_access_window_s and rec.access_count >= 2:
            return BlockTemperature.HOT
        if age <= self.warm_access_window_s:
            return BlockTemperature.WARM
        return BlockTemperature.COLD

    def score(self, rec: PhysicalBlockRecord, now: float | None = None) -> float:
        """Higher score => more eligible for demotion."""
        now = time.time() if now is None else now
        age = max(0.0, now - rec.last_access)
        freq = max(1, rec.access_count)
        temp = self.temperature(rec, now)
        temp_w = {"hot": 0.1, "warm": 1.0, "cold": 3.0}[temp.value]
        ref_w = 1.0 / float(max(1, rec.refcount))
        prio_w = 1.0 / float(max(1, rec.priority + 1))
        return (age / freq) * temp_w * ref_w * prio_w

    def next_colder(self, tier: StorageTier) -> StorageTier | None:
        try:
            idx = TIER_ORDER.index(tier)
        except ValueError:
            return StorageTier.L3_MEMORY_MAPPED
        if idx + 1 >= len(TIER_ORDER):
            return None
        return TIER_ORDER[idx + 1]

    def next_hotter(self, tier: StorageTier) -> StorageTier | None:
        try:
            idx = TIER_ORDER.index(tier)
        except ValueError:
            return StorageTier.L1_RAM
        if idx <= 0:
            return None
        return TIER_ORDER[idx - 1]


@dataclass
class KVTieringEngine:
    providers: ProviderRegistry
    physical: PhysicalBlockTable
    policy: TieringPolicy = field(default_factory=TieringPolicy)
    ram_budget_bytes: int = 512 * 1024 * 1024
    migrations: int = 0
    evictions: int = 0
    last_migration_latency_ms: float = 0.0

    def memory_pressure(self) -> float:
        ram = self.providers.ram_usage()
        return min(1.0, float(ram) / float(max(1, self.ram_budget_bytes)))

    def should_migrate(self) -> bool:
        return self.memory_pressure() >= self.policy.pressure_threshold

    def candidates_for_demotion(self, limit: int = 32) -> list[PhysicalBlockRecord]:
        now = time.time()
        records = [
            r
            for r in self.physical.all_records()
            if r.tier in (StorageTier.L1_RAM, StorageTier.L2_COMPRESSED_RAM)
        ]
        records.sort(key=lambda r: self.policy.score(r, now), reverse=True)
        return records[:limit]

    async def migrate_block(self, physical_id: str, target: StorageTier) -> bool:
        rec = self.physical.get(physical_id)
        if rec is None or rec.tier == target:
            return False
        if target in (StorageTier.FUTURE_CXL, StorageTier.FUTURE_MTE):
            raise NotImplementedError(f"cannot migrate to future tier {target}")
        start = time.monotonic()
        source_tier = rec.tier
        src = self.providers.get_tier(source_tier)
        dst = self.providers.get_tier(target)
        if src is None or dst is None:
            logger.warning(
                "migration_skipped id=%s from=%s to=%s reason=missing_provider",
                physical_id,
                int(source_tier),
                int(target),
            )
            return False
        data = await src.get(rec.provider_key)
        await dst.put(rec.provider_key, data)
        await src.delete(rec.provider_key)
        rec.temperature = self.policy.temperature(rec)
        rec.compressed = target != StorageTier.L1_RAM
        self.physical.update_tier(physical_id, target, rec.provider_key)
        self.migrations += 1
        self.last_migration_latency_ms = (time.monotonic() - start) * 1000.0
        logger.info(
            "migrated physical_id=%s from=%s to=%s latency_ms=%.2f",
            physical_id,
            int(source_tier),
            int(target),
            self.last_migration_latency_ms,
        )
        return True

    async def demote_under_pressure(self, limit: int = 16) -> int:
        if not self.should_migrate():
            return 0
        moved = 0
        for rec in self.candidates_for_demotion(limit=limit):
            target = self.policy.next_colder(rec.tier)
            if target is None:
                continue
            try:
                ok = await self.migrate_block(rec.physical_id, target)
            except Exception as exc:
                logger.warning("migration_failed id=%s err=%s", rec.physical_id, exc)
                continue
            if ok:
                moved += 1
                self.evictions += 1
            if not self.should_migrate():
                break
        return moved

    def dominant_tier(self) -> StorageTier:
        counts: dict[StorageTier, int] = {}
        for rec in self.physical.all_records():
            counts[rec.tier] = counts.get(rec.tier, 0) + 1
        if not counts:
            return StorageTier.L1_RAM
        return max(counts.items(), key=lambda kv: kv[1])[0]

    def fragmentation(self) -> float:
        """Simple fragmentation proxy: free logical holes / total (0 if dense)."""
        records = self.physical.all_records()
        if not records:
            return 0.0
        shared = sum(1 for r in records if r.refcount > 1)
        return min(1.0, float(shared) / float(len(records)))
