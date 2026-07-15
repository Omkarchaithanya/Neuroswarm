"""ARC-inspired eviction (ghost lists T1/T2 approximation)."""

from __future__ import annotations

from collections import OrderedDict

from ..interfaces import IEvictionPolicy
from ..models import KVRegistryRecord
from .lru import _pick


class ARCPolicy(IEvictionPolicy):
    """Approximate ARC: prefer cold infrequent over hot frequent."""

    def __init__(self) -> None:
        self._t1: OrderedDict[str, None] = OrderedDict()
        self._t2: OrderedDict[str, None] = OrderedDict()

    def observe(self, kv_id: str, *, frequent: bool = False) -> None:
        if frequent:
            self._t1.pop(kv_id, None)
            self._t2[kv_id] = None
            self._t2.move_to_end(kv_id)
        else:
            self._t2.pop(kv_id, None)
            self._t1[kv_id] = None
            self._t1.move_to_end(kv_id)

    def select_victims(
        self,
        records: list[KVRegistryRecord],
        *,
        bytes_needed: int = 0,
        count: int = 1,
    ) -> list[str]:
        by_id = {r.kv_id: r for r in records if not r.pinned and r.refcount <= 1}
        ordered: list[KVRegistryRecord] = []
        for kid in list(self._t1.keys()):
            if kid in by_id:
                ordered.append(by_id.pop(kid))
        # remaining never seen in ARC lists — treat as coldest
        ordered.extend(sorted(by_id.values(), key=lambda r: r.last_access))
        # t2 victims only if still need more
        return _pick(ordered, bytes_needed=bytes_needed, count=count)
