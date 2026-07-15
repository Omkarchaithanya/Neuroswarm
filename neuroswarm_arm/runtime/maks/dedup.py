"""Deduplication engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock

from .exceptions import KVDedupCollisionError
from .hashing import build_hasher
from .interfaces import IHasher
from .models import HashAlgo, KVIdentity


@dataclass
class DedupEntry:
    dedup_key: str
    kv_id: str
    content_hash: str
    identity_fp: str
    reuse_count: int = 0
    collisions: int = 0


@dataclass
class DedupStats:
    lookups: int = 0
    hits: int = 0
    misses: int = 0
    inserts: int = 0
    collisions: int = 0

    @property
    def hit_rate(self) -> float:
        if self.lookups == 0:
            return 0.0
        return self.hits / self.lookups

    @property
    def dedup_ratio(self) -> float:
        total = self.hits + self.inserts
        if total == 0:
            return 0.0
        return self.hits / total


class DeduplicationEngine:
    """Lookup / register by composite identity + prompt + content."""

    def __init__(self, hasher: IHasher | None = None, *, algo: HashAlgo = HashAlgo.SHA256) -> None:
        self.hasher = hasher or build_hasher(algo)
        self._by_key: dict[str, DedupEntry] = {}
        self._content_to_key: dict[str, str] = {}
        self.stats = DedupStats()
        self._lock = RLock()

    def make_key(
        self,
        identity: KVIdentity,
        *,
        prompt_prefix: bytes | str = b"",
        content_hash: str = "",
    ) -> str:
        ident_h = self.hasher.hash_identity(identity, prompt_prefix=prompt_prefix)
        if content_hash:
            return f"{ident_h}:{content_hash}"
        return ident_h

    def lookup(
        self,
        identity: KVIdentity,
        *,
        prompt_prefix: bytes | str = b"",
        content_hash: str = "",
    ) -> DedupEntry | None:
        key = self.make_key(identity, prompt_prefix=prompt_prefix, content_hash=content_hash)
        with self._lock:
            self.stats.lookups += 1
            ent = self._by_key.get(key)
            if ent is None:
                self.stats.misses += 1
                return None
            ent.reuse_count += 1
            self.stats.hits += 1
            return ent

    def register(
        self,
        kv_id: str,
        identity: KVIdentity,
        *,
        prompt_prefix: bytes | str = b"",
        content_hash: str = "",
        payload: bytes | None = None,
    ) -> DedupEntry:
        if payload is not None and not content_hash:
            content_hash = self.hasher.hash(payload)
        key = self.make_key(identity, prompt_prefix=prompt_prefix, content_hash=content_hash)
        with self._lock:
            existing = self._by_key.get(key)
            if existing is not None:
                if existing.content_hash and content_hash and existing.content_hash != content_hash:
                    existing.collisions += 1
                    self.stats.collisions += 1
                    raise KVDedupCollisionError(f"collision on dedup_key={key}")
                existing.reuse_count += 1
                self.stats.hits += 1
                return existing
            # Secondary collision check: same content hash, different identity key
            if content_hash and content_hash in self._content_to_key:
                other_key = self._content_to_key[content_hash]
                if other_key != key:
                    self.stats.collisions += 1
            ent = DedupEntry(
                dedup_key=key,
                kv_id=kv_id,
                content_hash=content_hash,
                identity_fp=identity.fingerprint(),
            )
            self._by_key[key] = ent
            if content_hash:
                self._content_to_key[content_hash] = key
            self.stats.inserts += 1
            return ent

    def forget(self, dedup_key: str) -> None:
        with self._lock:
            ent = self._by_key.pop(dedup_key, None)
            if ent and ent.content_hash:
                self._content_to_key.pop(ent.content_hash, None)
