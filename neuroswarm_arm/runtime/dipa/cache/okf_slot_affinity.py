"""OKF block-hash to llama-server id_slot affinity with TTL."""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass

try:
    import blake3 as _blake3
except ImportError:  # gateway image may omit optional blake3 wheel
    _blake3 = None


@dataclass(slots=True)
class _Mapping:
    slot_id: int
    recorded_at: float


class BlockHashSlotAffinity:
    """Deterministic block-hash → slot mapping for KV cache reuse."""

    def __init__(self, num_slots: int, ttl_seconds: int = 300) -> None:
        if num_slots < 1:
            raise ValueError("num_slots must be >= 1")
        self._num_slots = int(num_slots)
        self._ttl_seconds = float(ttl_seconds)
        self._lock = threading.RLock()
        self._mappings: dict[str, _Mapping] = {}
        self._hits = 0
        self._misses = 0
        self._evictions_total = 0

    @property
    def num_slots(self) -> int:
        return self._num_slots

    @staticmethod
    def _tool_ids_blob(tool_ids: tuple[str, ...] = ()) -> bytes:
        """Mix sorted tool ids with ASCII unit separator (never in tool names)."""
        # Empty / all-empty strings → no mix (byte-identical to content-only path).
        cleaned = tuple(t for t in tool_ids if t)
        if not cleaned:
            return b""
        return "\x1f".join(sorted(cleaned)).encode("utf-8")

    def hash_block(self, content: bytes | str, tool_ids: tuple[str, ...] = ()) -> str:
        """Hash content; optional tool_ids namespace the slot key."""
        data = content.encode("utf-8") if isinstance(content, str) else content
        blob = self._tool_ids_blob(tool_ids)
        if blob:
            data = data + blob
        if _blake3 is not None:
            return _blake3.blake3(data).hexdigest()
        return hashlib.sha256(data).hexdigest()

    def get_slot(self, block_hash: str, tool_ids: tuple[str, ...] = ()) -> int | None:
        """Get slot for block hash; tool_ids namespace the lookup key when non-empty."""
        blob = self._tool_ids_blob(tool_ids)
        lookup_key = f"{blob.decode('utf-8')}\x1f{block_hash}" if blob else block_hash

        now = time.monotonic()
        with self._lock:
            entry = self._mappings.get(lookup_key)
            if entry is None:
                self._misses += 1
                return None
            if (now - entry.recorded_at) > self._ttl_seconds:
                del self._mappings[lookup_key]
                self._evictions_total += 1
                self._misses += 1
                return None
            self._hits += 1
            return int(entry.slot_id)

    def assign_slot(
        self, block_hash: str, slot_id: int, tool_ids: tuple[str, ...] = ()
    ) -> None:
        """Assign slot for block hash; tool_ids namespace the key when non-empty."""
        slot = int(slot_id)
        if slot < 0 or slot >= self._num_slots:
            raise ValueError(f"slot_id {slot} out of range [0, {self._num_slots})")
        now = time.monotonic()
        blob = self._tool_ids_blob(tool_ids)
        lookup_key = f"{blob.decode('utf-8')}\x1f{block_hash}" if blob else block_hash
        with self._lock:
            self._mappings[lookup_key] = _Mapping(slot_id=slot, recorded_at=now)

    def evict_expired(self) -> int:
        now = time.monotonic()
        evicted = 0
        with self._lock:
            stale = [
                h
                for h, entry in self._mappings.items()
                if (now - entry.recorded_at) > self._ttl_seconds
            ]
            for h in stale:
                del self._mappings[h]
                evicted += 1
            self._evictions_total += evicted
        return evicted

    def stats(self) -> dict[str, float | int]:
        with self._lock:
            lookups = self._hits + self._misses
            hit_rate = (self._hits / lookups) if lookups else 0.0
            return {
                "hit_rate": float(hit_rate),
                "active_mappings": len(self._mappings),
                "evictions_total": int(self._evictions_total),
            }
