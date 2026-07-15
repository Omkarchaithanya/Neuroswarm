"""Prefix cache engine — longest prefix match with LRU eviction."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from threading import RLock

from ..utils.hashing import prefix_block_hash


@dataclass
class PrefixCacheEntry:
    block_hash: str
    physical_id: str
    token_end: int
    parent_hash: str = ""


@dataclass
class PrefixMatchResult:
    matched_blocks: list[str] = field(default_factory=list)
    matched_hashes: list[str] = field(default_factory=list)
    matched_tokens: int = 0
    hit: bool = False


class PrefixCacheEngine:
    """Block-hash prefix cache following modern inference runtime patterns."""

    def __init__(self, capacity: int = 100_000) -> None:
        self._capacity = max(1, capacity)
        self._entries: OrderedDict[str, PrefixCacheEntry] = OrderedDict()
        self._lock = RLock()
        self.hits = 0
        self.misses = 0

    def insert(
        self,
        *,
        prefix_hash: str,
        block_payload: bytes,
        physical_id: str,
        token_end: int,
    ) -> str:
        block_hash = prefix_block_hash(prefix_hash, block_payload)
        with self._lock:
            if block_hash in self._entries:
                self._entries.move_to_end(block_hash)
                return block_hash
            self._entries[block_hash] = PrefixCacheEntry(
                block_hash=block_hash,
                physical_id=physical_id,
                token_end=token_end,
                parent_hash=prefix_hash,
            )
            self._entries.move_to_end(block_hash)
            while len(self._entries) > self._capacity:
                self._entries.popitem(last=False)
        return block_hash

    def lookup(self, block_hash: str) -> PrefixCacheEntry | None:
        with self._lock:
            entry = self._entries.get(block_hash)
            if entry is None:
                return None
            self._entries.move_to_end(block_hash)
            return entry

    def longest_prefix_match(self, block_payloads: list[bytes]) -> PrefixMatchResult:
        """Search sequential block payloads for longest reusable prefix."""
        result = PrefixMatchResult()
        running = ""
        with self._lock:
            for payload in block_payloads:
                h = prefix_block_hash(running, payload)
                entry = self._entries.get(h)
                if entry is None:
                    break
                self._entries.move_to_end(h)
                result.matched_blocks.append(entry.physical_id)
                result.matched_hashes.append(h)
                result.matched_tokens = entry.token_end
                running = h
            if result.matched_blocks:
                self.hits += 1
                result.hit = True
            else:
                self.misses += 1
        return result

    def evict(self, block_hash: str) -> None:
        with self._lock:
            self._entries.pop(block_hash, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return float(self.hits) / float(total) if total else 0.0

    @property
    def miss_rate(self) -> float:
        return 1.0 - self.hit_rate if (self.hits + self.misses) else 0.0
