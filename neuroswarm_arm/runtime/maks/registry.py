"""In-memory KV registry with optional durable store."""

from __future__ import annotations

from threading import RLock

from .interfaces import IRegistryStore
from .metadata import now_ts
from .models import KVRegistryRecord, KVState, KVTier


class MemoryRegistryStore(IRegistryStore):
    def __init__(self) -> None:
        self._records: dict[str, KVRegistryRecord] = {}
        self._dedup: dict[str, str] = {}
        self._prompt: dict[str, set[str]] = {}
        self._lock = RLock()

    async def put(self, record: KVRegistryRecord) -> None:
        with self._lock:
            self._records[record.kv_id] = record
            if record.dedup_key:
                self._dedup[record.dedup_key] = record.kv_id
            if record.prompt_hash:
                self._prompt.setdefault(record.prompt_hash, set()).add(record.kv_id)

    async def get(self, kv_id: str) -> KVRegistryRecord | None:
        with self._lock:
            return self._records.get(kv_id)

    async def delete(self, kv_id: str) -> None:
        with self._lock:
            rec = self._records.pop(kv_id, None)
            if rec is None:
                return
            if rec.dedup_key and self._dedup.get(rec.dedup_key) == kv_id:
                self._dedup.pop(rec.dedup_key, None)
            if rec.prompt_hash:
                s = self._prompt.get(rec.prompt_hash)
                if s is not None:
                    s.discard(kv_id)
                    if not s:
                        self._prompt.pop(rec.prompt_hash, None)

    async def list_ids(self) -> list[str]:
        with self._lock:
            return list(self._records.keys())

    async def find_by_dedup(self, dedup_key: str) -> KVRegistryRecord | None:
        with self._lock:
            kid = self._dedup.get(dedup_key)
            if kid is None:
                return None
            return self._records.get(kid)

    async def find_by_prefix(self, prompt_hash: str) -> list[KVRegistryRecord]:
        with self._lock:
            exact = [self._records[i] for i in self._prompt.get(prompt_hash, set()) if i in self._records]
            # Partial prefix: prompt_hash is prefix of stored hash
            if exact:
                return exact
            out: list[KVRegistryRecord] = []
            for ph, ids in self._prompt.items():
                if ph.startswith(prompt_hash) or prompt_hash.startswith(ph):
                    for i in ids:
                        if i in self._records:
                            out.append(self._records[i])
            return out


class KVRegistry:
    """Layer-5 registry: memory index + optional durable backend."""

    def __init__(self, store: IRegistryStore | None = None) -> None:
        self.memory = MemoryRegistryStore()
        self.store = store
        self._lock = RLock()

    async def upsert(self, record: KVRegistryRecord) -> KVRegistryRecord:
        record.last_access = now_ts()
        await self.memory.put(record)
        if self.store is not None:
            await self.store.put(record)
        return record

    async def get(self, kv_id: str) -> KVRegistryRecord | None:
        rec = await self.memory.get(kv_id)
        if rec is not None:
            return rec
        if self.store is None:
            return None
        rec = await self.store.get(kv_id)
        if rec is not None:
            await self.memory.put(rec)
        return rec

    async def delete(self, kv_id: str) -> None:
        await self.memory.delete(kv_id)
        if self.store is not None:
            await self.store.delete(kv_id)

    async def list_ids(self) -> list[str]:
        ids = set(await self.memory.list_ids())
        if self.store is not None:
            ids.update(await self.store.list_ids())
        return sorted(ids)

    async def find_by_dedup(self, dedup_key: str) -> KVRegistryRecord | None:
        rec = await self.memory.find_by_dedup(dedup_key)
        if rec is not None:
            return rec
        if self.store is None:
            return None
        rec = await self.store.find_by_dedup(dedup_key)
        if rec is not None:
            await self.memory.put(rec)
        return rec

    async def find_by_prefix(self, prompt_hash: str) -> list[KVRegistryRecord]:
        mem = await self.memory.find_by_prefix(prompt_hash)
        if mem:
            return mem
        if self.store is None:
            return []
        return await self.store.find_by_prefix(prompt_hash)

    async def touch(self, kv_id: str, *, hit: bool = True) -> KVRegistryRecord | None:
        rec = await self.get(kv_id)
        if rec is None:
            return None
        rec.last_access = now_ts()
        rec.access_count += 1
        if hit:
            rec.metadata.hit_count += 1
            rec.metadata.reuse_count += 1
        else:
            rec.metadata.miss_count += 1
        return await self.upsert(rec)

    async def set_state(self, kv_id: str, state: KVState) -> KVRegistryRecord | None:
        rec = await self.get(kv_id)
        if rec is None:
            return None
        rec.state = state
        if state is KVState.PINNED:
            rec.pinned = True
        if state in {KVState.SHARED, KVState.WARMED, KVState.MIGRATED}:
            pass
        if state is KVState.RELEASED:
            rec.pinned = False
        return await self.upsert(rec)

    async def set_tier(self, kv_id: str, tier: KVTier) -> KVRegistryRecord | None:
        rec = await self.get(kv_id)
        if rec is None:
            return None
        rec.tier = tier
        return await self.upsert(rec)

    async def all_records(self) -> list[KVRegistryRecord]:
        out: list[KVRegistryRecord] = []
        for kid in await self.list_ids():
            rec = await self.get(kid)
            if rec is not None:
                out.append(rec)
        return out
