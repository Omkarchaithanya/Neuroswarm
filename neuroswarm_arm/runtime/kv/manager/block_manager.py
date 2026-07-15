"""KV Block Manager — fixed-size block allocation and session tables."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import RLock

from ..allocator.numa import LocalRAMAllocator, NUMAPlacementPolicy
from ..block.cow import CopyOnWriteEngine
from ..block.models import Block, SessionBlockTable
from ..block.tables import LogicalBlockTable, PhysicalBlockTable
from ..interfaces.types import (
    BlockStatus,
    BlockTemperature,
    PhysicalBlockRecord,
    StorageTier,
    TensorMeta,
)
from ..providers.registry import ProviderRegistry
from ..utils.hashing import content_hash, prefix_block_hash, stable_id
from ..utils.logging import get_logger
from .dedup import DeduplicationEngine
from .prefix import PrefixCacheEngine, PrefixMatchResult

logger = get_logger("neuroswarm.kv.block_manager")


@dataclass
class AllocateRequest:
    session_id: str
    payload: bytes
    layer: int = 0
    head: int = 0
    token_start: int = 0
    token_end: int = 0
    priority: int = 0
    agent_id: str = ""
    prefix_hash: str = ""
    meta: TensorMeta | None = None


@dataclass
class KVBlockManager:
    """Manages logical/physical mapping, prefix reuse, dedup, and CoW."""

    providers: ProviderRegistry
    physical: PhysicalBlockTable = field(default_factory=PhysicalBlockTable)
    prefix_cache: PrefixCacheEngine = field(default_factory=PrefixCacheEngine)
    numa_policy: NUMAPlacementPolicy = field(default_factory=NUMAPlacementPolicy)
    allocator: LocalRAMAllocator | None = None
    block_size_tokens: int = 256
    sessions: dict[str, SessionBlockTable] = field(default_factory=dict)
    logical_tables: dict[str, LogicalBlockTable] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def __post_init__(self) -> None:
        if self.allocator is None:
            node = self.numa_policy.choose_node()
            self.allocator = LocalRAMAllocator(node_id=node)
        self.dedup = DeduplicationEngine(self.physical)
        self.cow = CopyOnWriteEngine(self.physical)

    def create_session(self, session_id: str, *, agent_id: str = "") -> SessionBlockTable:
        with self._lock:
            if session_id in self.sessions:
                return self.sessions[session_id]
            now = time.time()
            table = SessionBlockTable(
                session_id=session_id,
                agent_id=agent_id,
                block_size_tokens=self.block_size_tokens,
                created_at=now,
                updated_at=now,
            )
            self.sessions[session_id] = table
            self.logical_tables[session_id] = LogicalBlockTable(session_id)
            return table

    def get_session(self, session_id: str) -> SessionBlockTable | None:
        with self._lock:
            return self.sessions.get(session_id)

    async def allocate(self, req: AllocateRequest) -> Block:
        session = self.create_session(req.session_id, agent_id=req.agent_id)
        now = time.time()
        meta = req.meta or TensorMeta(nbytes=len(req.payload), shape=(len(req.payload),))
        token_end = req.token_end or (req.token_start + self.block_size_tokens)

        # Dedup first
        existing = self.dedup.find(req.payload)
        if existing is not None:
            self.physical.acquire(existing.physical_id)
            block = self._attach_logical(
                session,
                physical=existing,
                layer=req.layer,
                head=req.head,
                token_start=req.token_start,
                token_end=token_end,
                prefix_hash=req.prefix_hash or existing.prefix_hash,
                now=now,
                priority=req.priority,
            )
            self.prefix_cache.insert(
                prefix_hash=block.prefix_hash,
                block_payload=req.payload,
                physical_id=existing.physical_id,
                token_end=token_end,
            )
            return block

        node = self.numa_policy.choose_node()
        provider = self.providers.for_tier(StorageTier.L1_RAM)
        physical_id = stable_id("phys")
        provider_key = physical_id
        await provider.put(provider_key, req.payload)

        prefix = req.prefix_hash
        block_hash = prefix_block_hash(prefix, req.payload)
        record = PhysicalBlockRecord(
            physical_id=physical_id,
            content_hash=content_hash(req.payload),
            prefix_hash=prefix,
            tier=StorageTier.L1_RAM,
            provider_key=provider_key,
            refcount=1,
            numa_node=node,
            layer=req.layer,
            head=req.head,
            token_start=req.token_start,
            token_end=token_end,
            status=BlockStatus.ALLOCATED,
            temperature=BlockTemperature.HOT,
            last_access=now,
            access_count=1,
            priority=req.priority,
            nbytes=len(req.payload),
            meta=meta,
        )
        result = self.dedup.register_or_reuse(record, req.payload)
        if result.reused and result.physical_id != physical_id:
            await provider.delete(provider_key)
            physical_id = result.physical_id
            record = self.physical.get(physical_id)  # type: ignore[assignment]

        assert record is not None
        block = self._attach_logical(
            session,
            physical=record,
            layer=req.layer,
            head=req.head,
            token_start=req.token_start,
            token_end=token_end,
            prefix_hash=prefix,
            now=now,
            priority=req.priority,
        )
        # Chain prefix: completed block hash becomes next prefix root
        block.prefix_hash = prefix
        block.content_hash = block_hash
        self.prefix_cache.insert(
            prefix_hash=prefix,
            block_payload=req.payload,
            physical_id=record.physical_id,
            token_end=token_end,
        )
        session.updated_at = now
        return block

    def _attach_logical(
        self,
        session: SessionBlockTable,
        *,
        physical: PhysicalBlockRecord,
        layer: int,
        head: int,
        token_start: int,
        token_end: int,
        prefix_hash: str,
        now: float,
        priority: int,
    ) -> Block:
        logical = self.logical_tables[session.session_id]
        idx = len(logical)
        block_id = stable_id("log")
        block = Block(
            id=block_id,
            layer=layer,
            head=head,
            token_start=token_start,
            token_end=token_end,
            reference_count=physical.refcount,
            content_hash=physical.content_hash,
            prefix_hash=prefix_hash,
            storage_tier=physical.tier,
            status=physical.status,
            temperature=physical.temperature,
            physical_id=physical.physical_id,
            numa_node=physical.numa_node,
            last_access=now,
            access_count=1,
            priority=priority,
            meta=physical.meta,
        )
        with self._lock:
            session.blocks[block_id] = block
            session.logical.append(block_id)
            logical.map(idx, physical.physical_id)
        return block

    async def release_session(self, session_id: str) -> None:
        with self._lock:
            session = self.sessions.pop(session_id, None)
            logical = self.logical_tables.pop(session_id, None)
        if session is None:
            return
        seen: set[str] = set()
        for block in session.blocks.values():
            pid = block.physical_id
            if not pid or pid in seen:
                continue
            seen.add(pid)
            remaining = self.physical.release(pid)
            if remaining == 0:
                # Best-effort delete across registered tiers only (skip missing backends).
                for tier in (
                    StorageTier.L1_RAM,
                    StorageTier.L2_COMPRESSED_RAM,
                    StorageTier.L3_MEMORY_MAPPED,
                    StorageTier.L3_NVME,
                    StorageTier.L4_LMDB,
                    StorageTier.L5_REDIS,
                ):
                    provider = self.providers.get_tier(tier)
                    if provider is None:
                        continue
                    try:
                        if await provider.exists(pid):
                            await provider.delete(pid)
                            break
                    except Exception:
                        continue
        if logical is not None:
            logical.clear()

    async def read_payload(self, physical_id: str) -> bytes:
        rec = self.physical.get(physical_id)
        if rec is None:
            raise KeyError(physical_id)
        provider = self.providers.for_tier(rec.tier)
        data = await provider.get(rec.provider_key)
        self.physical.touch(physical_id, time.time())
        return data

    async def write_cow(self, physical_id: str, payload: bytes) -> PhysicalBlockRecord:
        if not self.cow.needs_cow(physical_id):
            rec = self.physical.get(physical_id)
            if rec is None:
                raise KeyError(physical_id)
            provider = self.providers.for_tier(rec.tier)
            await provider.put(rec.provider_key, payload)
            rec.content_hash = content_hash(payload)
            rec.nbytes = len(payload)
            return rec
        provider = self.providers.for_tier(StorageTier.L1_RAM)
        clone = self.cow.clone(physical_id, payload, provider_key=stable_id("phys"))
        await provider.put(clone.provider_key, payload)
        self.providers.for_tier(StorageTier.L1_RAM)  # ensure L1
        clone.tier = StorageTier.L1_RAM
        self.physical.update_tier(clone.physical_id, StorageTier.L1_RAM, clone.provider_key)
        return clone

    def lookup_prefix(self, block_payloads: list[bytes]) -> PrefixMatchResult:
        return self.prefix_cache.longest_prefix_match(block_payloads)

    def reuse_prefix(
        self,
        session_id: str,
        match: PrefixMatchResult,
        *,
        agent_id: str = "",
    ) -> list[Block]:
        session = self.create_session(session_id, agent_id=agent_id)
        now = time.time()
        out: list[Block] = []
        for pid in match.matched_blocks:
            rec = self.physical.get(pid)
            if rec is None:
                break
            self.physical.acquire(pid)
            block = self._attach_logical(
                session,
                physical=rec,
                layer=rec.layer,
                head=rec.head,
                token_start=rec.token_start,
                token_end=rec.token_end,
                prefix_hash=rec.prefix_hash,
                now=now,
                priority=rec.priority,
            )
            out.append(block)
        return out
