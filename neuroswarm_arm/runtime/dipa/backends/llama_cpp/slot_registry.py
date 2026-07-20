"""Session-to-slot bindings for llama-server KV reuse."""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock


@dataclass(slots=True)
class SlotBinding:
    session_id: str
    id_slot: int
    tier_url: str
    filename: str = ""
    last_used_at: float = 0.0


class SlotRegistry:
    """Maps (session_id, tier_url) to llama-server slot indices."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._by_key: dict[tuple[str, str], SlotBinding] = {}

    def bind(
        self,
        session_id: str,
        id_slot: int,
        tier_url: str,
        *,
        filename: str = "",
    ) -> SlotBinding:
        key = (session_id, tier_url.rstrip("/"))
        binding = SlotBinding(
            session_id=session_id,
            id_slot=int(id_slot),
            tier_url=tier_url.rstrip("/"),
            filename=filename,
            last_used_at=time.time(),
        )
        with self._lock:
            self._by_key[key] = binding
        return binding

    def lookup(self, session_id: str, tier_url: str) -> int | None:
        key = (session_id, tier_url.rstrip("/"))
        with self._lock:
            binding = self._by_key.get(key)
            if binding is None:
                return None
            binding.last_used_at = time.time()
            return binding.id_slot

    def get_binding(self, session_id: str, tier_url: str) -> SlotBinding | None:
        key = (session_id, tier_url.rstrip("/"))
        with self._lock:
            return self._by_key.get(key)

    def set_filename(self, session_id: str, tier_url: str, filename: str) -> None:
        key = (session_id, tier_url.rstrip("/"))
        with self._lock:
            binding = self._by_key.get(key)
            if binding is not None:
                binding.filename = filename

    def release(self, session_id: str, tier_url: str) -> None:
        key = (session_id, tier_url.rstrip("/"))
        with self._lock:
            self._by_key.pop(key, None)

    def evict_lru(self, tier_url: str) -> tuple[str, int] | None:
        tier = tier_url.rstrip("/")
        with self._lock:
            candidates = [
                (k, b)
                for k, b in self._by_key.items()
                if k[1] == tier
            ]
            if not candidates:
                return None
            candidates.sort(key=lambda item: item[1].last_used_at)
            (session_id, _tier), binding = candidates[0]
            self._by_key.pop((session_id, _tier), None)
            return session_id, binding.id_slot

    def snapshot(self) -> list[dict[str, object]]:
        with self._lock:
            return [
                {
                    "session_id": b.session_id,
                    "id_slot": b.id_slot,
                    "tier_url": b.tier_url,
                    "filename": b.filename,
                    "last_used_at": b.last_used_at,
                }
                for b in self._by_key.values()
            ]


_GLOBAL_REGISTRY: SlotRegistry | None = None


def get_slot_registry() -> SlotRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = SlotRegistry()
    return _GLOBAL_REGISTRY
