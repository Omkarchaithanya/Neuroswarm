"""KVCacheManager — session KV handles via connector (no GGML internals)."""

from __future__ import annotations

import threading
import time
from typing import Any, Mapping

from neuroswarm_arm.runtime.dipa.interfaces.kv_cache import IKVCacheConnector


class KVCacheManager:
    def __init__(self, connector: IKVCacheConnector | None = None) -> None:
        self.connector = connector
        self._lock = threading.RLock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._allocs = 0
        self._hits = 0
        self._misses = 0

    def attach(self, connector: IKVCacheConnector) -> None:
        self.connector = connector

    def allocate(
        self,
        session_id: str,
        *,
        agent_id: str = "default",
        prompt_hash: str = "",
        size_hint: int = 0,
    ) -> dict[str, Any]:
        with self._lock:
            self._allocs += 1
            handle = {
                "session_id": session_id,
                "agent_id": agent_id,
                "prompt_hash": prompt_hash,
                "size_hint": size_hint,
                "allocated_at": time.time(),
                "backend_handle": None,
            }
            if self.connector is not None:
                try:
                    # Connector APIs vary; best-effort lookup/create hooks.
                    lookup = getattr(self.connector, "lookup", None)
                    if callable(lookup) and prompt_hash:
                        existing = lookup(prompt_hash=prompt_hash)
                        if existing is not None:
                            self._hits += 1
                            handle["backend_handle"] = existing
                            self._sessions[session_id] = handle
                            return handle
                    self._misses += 1
                except Exception:
                    self._misses += 1
            self._sessions[session_id] = handle
            return handle

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._sessions.get(session_id)

    def release(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def snapshot(self) -> Mapping[str, Any]:
        with self._lock:
            return {
                "sessions": len(self._sessions),
                "allocs": self._allocs,
                "hits": self._hits,
                "misses": self._misses,
                "connector": self.connector is not None,
            }
