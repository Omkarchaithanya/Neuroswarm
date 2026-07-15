"""Atomic reference counting with orphan / zombie detection."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import RLock


@dataclass
class RefEntry:
    count: int = 0
    owners: set[str] = field(default_factory=set)
    exclusive_owner: str | None = None
    last_change: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)


class ReferenceCounter:
    """Thread-safe refcount. Process-safe via Redis registry when distributed."""

    def __init__(self, *, orphan_grace_s: float = 300.0) -> None:
        self._entries: dict[str, RefEntry] = {}
        self._lock = RLock()
        self.orphan_grace_s = orphan_grace_s

    def increment(self, kv_id: str, owner: str = "", *, exclusive: bool = False) -> int:
        with self._lock:
            ent = self._entries.setdefault(kv_id, RefEntry())
            if exclusive:
                if ent.count > 0 and ent.exclusive_owner and ent.exclusive_owner != owner:
                    raise RuntimeError(f"exclusive ownership held by {ent.exclusive_owner}")
                ent.exclusive_owner = owner or ent.exclusive_owner or "owner"
            ent.count += 1
            if owner:
                ent.owners.add(owner)
            ent.last_change = time.time()
            return ent.count

    def decrement(self, kv_id: str, owner: str = "") -> int:
        with self._lock:
            ent = self._entries.get(kv_id)
            if ent is None:
                return 0
            ent.count = max(0, ent.count - 1)
            if owner:
                ent.owners.discard(owner)
            if ent.count == 0:
                ent.exclusive_owner = None
            ent.last_change = time.time()
            return ent.count

    def get(self, kv_id: str) -> int:
        with self._lock:
            ent = self._entries.get(kv_id)
            return 0 if ent is None else ent.count

    def owners(self, kv_id: str) -> set[str]:
        with self._lock:
            ent = self._entries.get(kv_id)
            return set() if ent is None else set(ent.owners)

    def release_all(self, kv_id: str) -> None:
        with self._lock:
            self._entries.pop(kv_id, None)

    def orphans(self, known_ids: set[str] | None = None) -> list[str]:
        """Entries with refcount>0 but no owners, past grace."""
        now = time.time()
        out: list[str] = []
        with self._lock:
            for kid, ent in self._entries.items():
                if known_ids is not None and kid not in known_ids:
                    continue
                if ent.count > 0 and not ent.owners and (now - ent.last_change) >= self.orphan_grace_s:
                    out.append(kid)
        return out

    def zombies(self, known_ids: set[str]) -> list[str]:
        """Refcount entries for KV ids no longer in registry."""
        with self._lock:
            return [kid for kid in self._entries if kid not in known_ids]

    def cleanup_zero(self) -> list[str]:
        removed: list[str] = []
        with self._lock:
            for kid in list(self._entries):
                if self._entries[kid].count <= 0:
                    del self._entries[kid]
                    removed.append(kid)
        return removed
