"""Model warm pool tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import monotonic


@dataclass
class ModelSlot:
    model: str
    warm: bool = False
    last_used: float = field(default_factory=monotonic)
    hits: int = 0


class ModelPool:
    def __init__(self) -> None:
        self._lock = Lock()
        self._models: dict[str, ModelSlot] = {}

    def mark_warm(self, model: str) -> None:
        with self._lock:
            slot = self._models.setdefault(model, ModelSlot(model=model))
            slot.warm = True
            slot.last_used = monotonic()

    def touch(self, model: str) -> None:
        with self._lock:
            slot = self._models.setdefault(model, ModelSlot(model=model))
            slot.hits += 1
            slot.last_used = monotonic()

    def is_warm(self, model: str) -> bool:
        with self._lock:
            slot = self._models.get(model)
            return bool(slot and slot.warm)

    def snapshot(self) -> dict[str, dict[str, object]]:
        with self._lock:
            return {
                k: {"warm": v.warm, "hits": v.hits, "last_used": v.last_used}
                for k, v in self._models.items()
            }
