"""KVCacheManager — session KV handles via connector (no GGML internals)."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Mapping

from neuroswarm_arm.runtime.dipa.interfaces.kv_cache import IKVCacheConnector

if TYPE_CHECKING:
    from neuroswarm_arm.runtime.dipa.control.telemetry_exporter import TelemetryExporter


class KVCacheManager:
    def __init__(
        self,
        connector: IKVCacheConnector | None = None,
        *,
        telemetry: TelemetryExporter | None = None,
    ) -> None:
        self.connector = connector
        self._telemetry = telemetry
        self._lock = threading.RLock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._allocs = 0
        self._hits = 0
        self._misses = 0

    def attach(self, connector: IKVCacheConnector) -> None:
        with self._lock:
            self.connector = connector

    @property
    def is_wired(self) -> bool:
        with self._lock:
            return self.connector is not None

    def _connector_ref(self) -> IKVCacheConnector | None:
        with self._lock:
            return self.connector

    async def load(self, session_id: str, agent_id: str = "") -> str | None:
        connector = self._connector_ref()
        if connector is None:
            return None
        tel = self._telemetry
        with tel.span(
            "neuroswarm.kv.load",
            session_id=session_id,
            agent_id=agent_id,
        ) if tel else _null_span():
            handle = await connector.load(session_id, agent_id)
        if tel:
            tel.record_kv_alloc(hit=handle is not None)
            tel.event(
                "neuroswarm.kv.load",
                session_id=session_id,
                kv_id=handle or "",
                cache_hit=bool(handle),
            )
        return handle

    async def save(
        self,
        session_id: str,
        payload: bytes,
        *,
        agent_id: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        connector = self._connector_ref()
        if connector is None:
            return session_id or agent_id or "anon"
        tel = self._telemetry
        with tel.span(
            "neuroswarm.kv.save",
            session_id=session_id,
            agent_id=agent_id,
            payload_bytes=len(payload),
        ) if tel else _null_span():
            key = await connector.save(
                session_id, payload, agent_id=agent_id, metadata=metadata
            )
        if tel:
            tel.event("neuroswarm.kv.save", session_id=session_id, kv_id=key)
        return key

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


@contextmanager
def _null_span():
    yield None
