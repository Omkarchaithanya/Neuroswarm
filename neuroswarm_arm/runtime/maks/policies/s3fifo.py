"""S3-FIFO eviction policy (small/main/ghost queues)."""

from __future__ import annotations

from collections import deque

from ..interfaces import IEvictionPolicy
from ..models import KVRegistryRecord
from .lru import _pick


class S3FIFOPolicy(IEvictionPolicy):
    """Approximate S3-FIFO: small probationary + main + ghost second-chance."""

    def __init__(self, *, small_ratio: float = 0.1) -> None:
        self.small_ratio = small_ratio
        self._small: deque[str] = deque()
        self._main: deque[str] = deque()
        self._ghost: set[str] = set()

    def observe(self, kv_id: str, *, frequent: bool = False) -> None:
        if frequent:
            if kv_id in self._ghost:
                self._ghost.discard(kv_id)
            if kv_id not in self._main:
                self._main.append(kv_id)
            return
        if kv_id not in self._small and kv_id not in self._main:
            self._small.append(kv_id)

    def select_victims(
        self,
        records: list[KVRegistryRecord],
        *,
        bytes_needed: int = 0,
        count: int = 1,
    ) -> list[str]:
        by_id = {r.kv_id: r for r in records if not r.pinned and r.refcount <= 1}
        ordered: list[KVRegistryRecord] = []
        for kid in list(self._small):
            if kid in by_id:
                ordered.append(by_id.pop(kid))
        for kid in list(self._main):
            if kid in by_id:
                ordered.append(by_id.pop(kid))
        ordered.extend(sorted(by_id.values(), key=lambda r: r.last_access))
        victims = _pick(ordered, bytes_needed=bytes_needed, count=count)
        for kid in victims:
            if kid in self._small:
                self._small.remove(kid)
            if kid in self._main:
                self._main.remove(kid)
            self._ghost.add(kid)
        return victims
