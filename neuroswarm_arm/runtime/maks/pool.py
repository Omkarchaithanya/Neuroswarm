"""Global KV Page Pool — Linux-like page table for MAKS Memory OS."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from .models import KVIdentity, KVTier, ProviderName


def new_page_id() -> str:
    return f"pg_{uuid.uuid4().hex}"


@dataclass
class PageMeta:
    """Metadata for one physical page in the global pool."""

    page_id: str
    kv_id: str = ""
    size_bytes: int = 0
    provider: ProviderName = ProviderName.RAM
    tier: KVTier = KVTier.HOT
    checksum: str = ""
    compression: str = "none"
    refcount: int = 0
    share_count: int = 0
    numa_node: int = 0
    backend_id: str = ""
    identity_fingerprint: str = ""
    content_hash: str = ""
    prefix_hash: str = ""
    version: int = 1
    cow: bool = False
    pinned: bool = False
    created_at: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)
    access_count: int = 0
    cascade_stage: int = 0
    reasoning_depth: int = 0
    importance: float = 0.0
    prediction_score: float = 0.0
    location: str = ""
    capabilities: dict[str, bool] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.last_access = time.time()
        self.access_count += 1


@dataclass
class PageTableEntry:
    """Logical handle → ordered physical pages (block table analogue)."""

    kv_id: str
    page_ids: list[str] = field(default_factory=list)
    identity: KVIdentity = field(default_factory=KVIdentity)
    token_count: int = 0
    version: int = 1


class GlobalPagePool:
    """Owns physical pages + page tables. Upper layers never touch provider bytes directly."""

    DEFAULT_PAGE_BYTES = 64 * 1024  # logical page size hint (opaque blob may be 1 page)

    def __init__(self, *, page_bytes: int = DEFAULT_PAGE_BYTES) -> None:
        self.page_bytes = max(1024, int(page_bytes))
        self._pages: dict[str, PageMeta] = {}
        self._tables: dict[str, PageTableEntry] = {}
        self._content_index: dict[str, str] = {}  # content_hash → page_id
        self._lock = RLock()

    def allocate_pages(
        self,
        kv_id: str,
        size_bytes: int,
        *,
        identity: KVIdentity | None = None,
        provider: ProviderName = ProviderName.RAM,
        location: str = "",
        checksum: str = "",
        content_hash: str = "",
        prefix_hash: str = "",
        compression: str = "none",
        numa_node: int = 0,
        backend_id: str = "",
        capabilities: dict[str, bool] | None = None,
        importance: float = 0.0,
        cascade_stage: int = 0,
        reasoning_depth: int = 0,
    ) -> PageTableEntry:
        """Register one or more pages for a logical KV handle."""
        ident = identity or KVIdentity()
        n_pages = max(1, (size_bytes + self.page_bytes - 1) // self.page_bytes)
        page_ids: list[str] = []
        rem = size_bytes
        with self._lock:
            for i in range(n_pages):
                psz = min(self.page_bytes, rem) if rem > 0 else 0
                rem = max(0, rem - psz)
                pid = new_page_id()
                meta = PageMeta(
                    page_id=pid,
                    kv_id=kv_id,
                    size_bytes=psz if psz > 0 else (size_bytes if n_pages == 1 else self.page_bytes),
                    provider=provider,
                    location=location,
                    checksum=checksum,
                    content_hash=content_hash,
                    prefix_hash=prefix_hash,
                    compression=compression,
                    numa_node=numa_node,
                    backend_id=backend_id,
                    identity_fingerprint=ident.fingerprint(),
                    capabilities=dict(capabilities or {}),
                    importance=importance,
                    cascade_stage=cascade_stage,
                    reasoning_depth=reasoning_depth,
                    refcount=1,
                )
                self._pages[pid] = meta
                if content_hash and i == 0:
                    self._content_index.setdefault(content_hash, pid)
                page_ids.append(pid)
            entry = PageTableEntry(
                kv_id=kv_id,
                page_ids=page_ids,
                identity=ident,
                token_count=0,
                version=1,
            )
            self._tables[kv_id] = entry
            return entry

    def get_table(self, kv_id: str) -> PageTableEntry | None:
        with self._lock:
            return self._tables.get(kv_id)

    def get_page(self, page_id: str) -> PageMeta | None:
        with self._lock:
            return self._pages.get(page_id)

    def pages_for(self, kv_id: str) -> list[PageMeta]:
        with self._lock:
            entry = self._tables.get(kv_id)
            if entry is None:
                return []
            return [self._pages[p] for p in entry.page_ids if p in self._pages]

    def touch(self, kv_id: str) -> None:
        with self._lock:
            for meta in self.pages_for_unlocked(kv_id):
                meta.touch()

    def pages_for_unlocked(self, kv_id: str) -> list[PageMeta]:
        entry = self._tables.get(kv_id)
        if entry is None:
            return []
        return [self._pages[p] for p in entry.page_ids if p in self._pages]

    def increment_share(self, kv_id: str) -> int:
        with self._lock:
            total = 0
            for meta in self.pages_for_unlocked(kv_id):
                meta.share_count += 1
                meta.refcount += 1
                total = meta.share_count
            return total

    def decrement_share(self, kv_id: str) -> int:
        with self._lock:
            total = 0
            for meta in self.pages_for_unlocked(kv_id):
                meta.share_count = max(0, meta.share_count - 1)
                meta.refcount = max(0, meta.refcount - 1)
                total = meta.refcount
            return total

    def mark_cow(self, kv_id: str) -> None:
        """Copy-on-write: shared pages become exclusive on next write."""
        with self._lock:
            for meta in self.pages_for_unlocked(kv_id):
                if meta.share_count > 0 or meta.refcount > 1:
                    meta.cow = True

    def snapshot(self, kv_id: str) -> PageTableEntry | None:
        """Version bump for snapshot support (logical CoW snapshot)."""
        with self._lock:
            entry = self._tables.get(kv_id)
            if entry is None:
                return None
            entry.version += 1
            for meta in self.pages_for_unlocked(kv_id):
                meta.version += 1
            return entry

    def set_tier(self, kv_id: str, tier: KVTier, provider: ProviderName | None = None) -> None:
        with self._lock:
            for meta in self.pages_for_unlocked(kv_id):
                meta.tier = tier
                if provider is not None:
                    meta.provider = provider

    def set_location(self, kv_id: str, location: str, provider: ProviderName) -> None:
        with self._lock:
            for meta in self.pages_for_unlocked(kv_id):
                meta.location = location
                meta.provider = provider

    def pin(self, kv_id: str) -> None:
        with self._lock:
            for meta in self.pages_for_unlocked(kv_id):
                meta.pinned = True

    def unpin(self, kv_id: str) -> None:
        with self._lock:
            for meta in self.pages_for_unlocked(kv_id):
                meta.pinned = False

    def release(self, kv_id: str) -> list[str]:
        """Drop page table; return freed page ids."""
        with self._lock:
            entry = self._tables.pop(kv_id, None)
            if entry is None:
                return []
            freed: list[str] = []
            for pid in entry.page_ids:
                meta = self._pages.pop(pid, None)
                if meta is None:
                    continue
                if meta.content_hash and self._content_index.get(meta.content_hash) == pid:
                    self._content_index.pop(meta.content_hash, None)
                freed.append(pid)
            return freed

    def find_by_content(self, content_hash: str) -> PageMeta | None:
        with self._lock:
            pid = self._content_index.get(content_hash)
            if not pid:
                return None
            return self._pages.get(pid)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            hot = warm = cold = 0
            used = 0
            shared = 0
            for meta in self._pages.values():
                used += meta.size_bytes
                if meta.share_count > 0:
                    shared += 1
                if meta.tier is KVTier.HOT:
                    hot += 1
                elif meta.tier is KVTier.WARM:
                    warm += 1
                else:
                    cold += 1
            return {
                "pages": len(self._pages),
                "handles": len(self._tables),
                "used_bytes": used,
                "shared_pages": shared,
                "hot_pages": hot,
                "warm_pages": warm,
                "cold_pages": cold,
            }

    def all_pages(self) -> list[PageMeta]:
        with self._lock:
            return list(self._pages.values())
