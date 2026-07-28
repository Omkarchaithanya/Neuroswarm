"""Memory warmer — pin Mem0 / NeuroMemory search hits into a short TTL cache."""

from __future__ import annotations

import time
from typing import Any, Mapping

from neuroswarm_arm.runtime.awpp.interfaces import IWarmer, WarmResult


class MemoryWarmer(IWarmer):
    """Prefetch memory search / predict_next results into an in-process pin cache."""

    kind = "memory"

    def __init__(
        self,
        memory: Any | None = None,
        *,
        ttl_s: float = 30.0,
        limit: int = 5,
    ) -> None:
        self.memory = memory
        self.ttl_s = ttl_s
        self.limit = limit
        self._cache: dict[str, tuple[float, list[Any]]] = {}

    def bind(self, memory: Any) -> None:
        self.memory = memory

    def _neuro(self) -> Any | None:
        mem = self.memory
        if mem is not None and hasattr(mem, "neuro"):
            return mem.neuro
        return mem

    async def warm(self, key: str, *, metadata: Mapping[str, Any] | None = None) -> WarmResult:
        t0 = time.perf_counter()
        meta = dict(metadata or {})
        owner = str(meta.get("agent_id") or meta.get("owner") or "default")
        neuro = self._neuro()
        hits: list[Any] = []
        if neuro is None:
            # Still mark as warmed so predictors can proceed without Mem0 in unit tests
            self._cache[key] = (time.time() + self.ttl_s, [])
            return WarmResult(
                target_kind=self.kind,
                target_key=key,
                success=True,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                metadata={"pinned": 0, "mode": "noop"},
            )
        try:
            if hasattr(neuro, "search_texts"):
                hits = list(neuro.search_texts(owner, key, limit=self.limit) or [])
            elif hasattr(neuro, "recall"):
                hits = list(neuro.recall(owner, key, limit=self.limit) or [])
            elif hasattr(neuro, "search"):
                hits = list(neuro.search(key, owner=owner, limit=self.limit) or [])
            if hasattr(neuro, "predict_next"):
                try:
                    neuro.predict_next(owner, context=key)
                except Exception:
                    pass
            self._cache[key] = (time.time() + self.ttl_s, hits)
            return WarmResult(
                target_kind=self.kind,
                target_key=key,
                success=True,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                bytes_touched=sum(len(str(h)) for h in hits),
                metadata={"pinned": len(hits), "mode": "search"},
            )
        except Exception as exc:  # noqa: BLE001
            return WarmResult(
                target_kind=self.kind,
                target_key=key,
                success=False,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                error=str(exc),
            )

    def is_warm(self, key: str) -> bool:
        entry = self._cache.get(key)
        if entry is None:
            return False
        expires, _ = entry
        if time.time() > expires:
            self._cache.pop(key, None)
            return False
        return True

    def get_pinned(self, key: str) -> list[Any]:
        if not self.is_warm(key):
            return []
        return list(self._cache[key][1])
