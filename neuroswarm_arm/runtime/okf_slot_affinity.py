"""OKF block-hash to llama-server id_slot affinity table."""

from __future__ import annotations

import os
import threading
from collections import OrderedDict


class OkfSlotAffinity:
    """LRU map from OKF block hash to last-used llama id_slot."""

    def __init__(self, max_entries: int | None = None) -> None:
        self._max = max_entries if max_entries is not None else int(
            os.getenv("NSA_OKF_AFFINITY_MAX", "256")
        )
        self._lock = threading.RLock()
        self._table: OrderedDict[str, int] = OrderedDict()

    def record(self, block_hashes: list[str], id_slot: int) -> None:
        if not block_hashes:
            return
        with self._lock:
            for h in block_hashes:
                if h in self._table:
                    del self._table[h]
                self._table[h] = int(id_slot)
            while len(self._table) > self._max:
                self._table.popitem(last=False)

    def lookup(self, block_hashes: list[str]) -> int | None:
        if not block_hashes:
            return None
        with self._lock:
            for h in block_hashes:
                if h in self._table:
                    self._table.move_to_end(h)
                    return int(self._table[h])
        return None

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._table)


def block_hashes_from_baggage(baggage: dict[str, object] | None) -> list[str]:
    if not baggage:
        return []
    hashes = baggage.get("okf_block_hashes")
    if isinstance(hashes, list) and hashes:
        return [str(h) for h in hashes]
    blocks = baggage.get("okf_blocks")
    if isinstance(blocks, list) and blocks:
        try:
            from nexus_okf.internal.hashutil import hash_block
        except ImportError:
            import hashlib

            def hash_block(data: bytes | str) -> str:
                if isinstance(data, str):
                    data = data.encode("utf-8")
                return hashlib.sha256(data).hexdigest()[:16]

        return [hash_block(str(b)) for b in blocks]
    return []
