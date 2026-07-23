"""Thread-safe session-to-physical-slot registry for llama-server KV reuse."""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock


@dataclass(slots=True)
class SlotMetadata:
    session_id: str
    slot_id: int
    last_used_timestamp: float
    prefix_hash: str = ""


class SlotRegistry:
    """Maps session_id to llama-server physical slot indices (0 .. total_slots - 1)."""

    def __init__(self, total_slots: int) -> None:
        if total_slots < 1:
            raise ValueError("total_slots must be >= 1")
        self._total_slots = int(total_slots)
        self._lock = RLock()
        self._session_to_slot: dict[str, int] = {}
        self._slots: dict[int, SlotMetadata] = {}

    @property
    def total_slots(self) -> int:
        return self._total_slots

    def acquire(self, session_id: str, prefix_hash: str = "") -> tuple[int, bool]:
        """Return (slot_id, slot_reused). Evict LRU session when all slots are occupied."""
        if not session_id:
            raise ValueError("session_id is required")

        with self._lock:
            existing = self._session_to_slot.get(session_id)
            if existing is not None:
                meta = self._slots[existing]
                meta.last_used_timestamp = time.time()
                if prefix_hash:
                    meta.prefix_hash = prefix_hash
                return existing, True

            occupied = set(self._slots.keys())
            free = [
                slot_id for slot_id in range(self._total_slots) if slot_id not in occupied
            ]
            if free:
                slot_id = min(free)
            else:
                lru_session, lru_slot = min(
                    self._session_to_slot.items(),
                    key=lambda item: self._slots[item[1]].last_used_timestamp,
                )
                self._session_to_slot.pop(lru_session, None)
                self._slots.pop(lru_slot, None)
                slot_id = lru_slot

            now = time.time()
            self._session_to_slot[session_id] = slot_id
            self._slots[slot_id] = SlotMetadata(
                session_id=session_id,
                slot_id=slot_id,
                last_used_timestamp=now,
                prefix_hash=prefix_hash,
            )
            return slot_id, False

    def lookup(self, session_id: str) -> int | None:
        with self._lock:
            slot_id = self._session_to_slot.get(session_id)
            if slot_id is None:
                return None
            meta = self._slots.get(slot_id)
            if meta is not None:
                meta.last_used_timestamp = time.time()
            return slot_id

    def get_metadata(self, slot_id: int) -> SlotMetadata | None:
        with self._lock:
            return self._slots.get(int(slot_id))

    def release(self, session_id: str) -> None:
        with self._lock:
            slot_id = self._session_to_slot.pop(session_id, None)
            if slot_id is not None:
                self._slots.pop(slot_id, None)

    def snapshot(self) -> list[SlotMetadata]:
        with self._lock:
            return list(self._slots.values())


_GLOBAL_REGISTRY: SlotRegistry | None = None
_GLOBAL_TOTAL_SLOTS: int = 8


def get_slot_registry(total_slots: int | None = None) -> SlotRegistry:
    global _GLOBAL_REGISTRY, _GLOBAL_TOTAL_SLOTS
    slots = int(total_slots) if total_slots is not None else _GLOBAL_TOTAL_SLOTS
    if _GLOBAL_REGISTRY is None or _GLOBAL_REGISTRY.total_slots != slots:
        _GLOBAL_REGISTRY = SlotRegistry(slots)
        _GLOBAL_TOTAL_SLOTS = slots
    return _GLOBAL_REGISTRY
