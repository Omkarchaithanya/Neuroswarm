"""Multi-tier Context Cache — LRU/LFU/TTL + version-aware invalidation."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from neuroswarm_arm.runtime.acr.ir.context import ContextSnapshot


@dataclass
class _Entry:
    snapshot: ContextSnapshot
    tier: str
    created: float
    hits: int = 0
    version_hash: str = ""
    deps: set[str] = field(default_factory=set)


class ContextCache:
    """Hot/Warm/Assembly/Compression/Memory/Knowledge/Planning/Prompt/NUMA/Shared."""

    TIERS = (
        "hot",
        "warm",
        "assembly",
        "compression",
        "memory",
        "knowledge",
        "planning",
        "prompt",
        "numa",
        "shared",
    )

    def __init__(
        self,
        max_entries: int = 256,
        ttl_s: float = 60.0,
        policy: str = "lru",  # lru | lfu
        numa_node: int | None = None,
    ) -> None:
        self.max_entries = max_entries
        self.ttl_s = ttl_s
        self.policy = policy
        self.numa_node = numa_node
        self._lock = threading.Lock()
        self._store: OrderedDict[str, _Entry] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key_digest: str) -> ContextSnapshot | None:
        with self._lock:
            entry = self._store.get(key_digest)
            if entry is None:
                self.misses += 1
                return None
            if self.ttl_s > 0 and (time.time() - entry.created) > self.ttl_s:
                del self._store[key_digest]
                self.misses += 1
                return None
            entry.hits += 1
            self.hits += 1
            if self.policy == "lru":
                self._store.move_to_end(key_digest)
            snap = entry.snapshot
            snap.stats.cache_hit = True
            snap.stats.cache_tier = entry.tier
            return snap

    def put(
        self,
        key_digest: str,
        snapshot: ContextSnapshot,
        *,
        tier: str = "hot",
        version_hash: str = "",
        deps: set[str] | None = None,
    ) -> None:
        tier = tier if tier in self.TIERS else "hot"
        with self._lock:
            self._store[key_digest] = _Entry(
                snapshot=snapshot,
                tier=tier,
                created=time.time(),
                version_hash=version_hash or snapshot.version.content_hash,
                deps=deps or set(),
            )
            self._store.move_to_end(key_digest)
            self._evict()

    def invalidate(self, *, prefix: str = "", version_hash: str = "", dep: str = "") -> int:
        with self._lock:
            keys = list(self._store.keys())
            removed = 0
            for k in keys:
                e = self._store[k]
                if prefix and not k.startswith(prefix) and prefix not in k:
                    # also match request fingerprint style
                    pass
                drop = False
                if version_hash and e.version_hash == version_hash:
                    drop = True
                if dep and dep in e.deps:
                    drop = True
                if prefix and prefix in k:
                    drop = True
                if drop:
                    del self._store[k]
                    removed += 1
            return removed

    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def stats(self) -> dict[str, Any]:
        return {
            "entries": len(self._store),
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": self.hit_ratio(),
            "numa_node": self.numa_node,
            "policy": self.policy,
        }

    def _evict(self) -> None:
        while len(self._store) > self.max_entries:
            if self.policy == "lfu":
                # Evict least-frequently used
                victim = min(self._store.items(), key=lambda kv: kv[1].hits)[0]
                del self._store[victim]
            else:
                self._store.popitem(last=False)
