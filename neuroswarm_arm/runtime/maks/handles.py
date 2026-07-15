"""Handle registry — logical session/handle ownership surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from .models import KVHandle, KVIdentity, ProviderName


@dataclass
class SessionBinding:
    session_id: str
    kv_id: str
    agent_id: str = ""
    identity: KVIdentity = field(default_factory=KVIdentity)
    backend_id: str = "opaque"
    created_at: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


class HandleRegistry:
    """Maps sessions / agents → KV handles without owning storage."""

    def __init__(self) -> None:
        self._by_session: dict[str, str] = {}
        self._by_kv: dict[str, SessionBinding] = {}
        self._lock = RLock()

    def bind(
        self,
        *,
        kv_id: str,
        session_id: str = "",
        agent_id: str = "",
        identity: KVIdentity | None = None,
        backend_id: str = "opaque",
        created_at: float = 0.0,
    ) -> SessionBinding:
        binding = SessionBinding(
            session_id=session_id or kv_id,
            kv_id=kv_id,
            agent_id=agent_id,
            identity=identity or KVIdentity(),
            backend_id=backend_id,
            created_at=created_at,
        )
        with self._lock:
            if session_id:
                self._by_session[session_id] = kv_id
            self._by_kv[kv_id] = binding
        return binding

    def resolve_session(self, session_id: str) -> str | None:
        with self._lock:
            return self._by_session.get(session_id)

    def get(self, kv_id: str) -> SessionBinding | None:
        with self._lock:
            return self._by_kv.get(kv_id)

    def unbind(self, kv_id: str) -> None:
        with self._lock:
            binding = self._by_kv.pop(kv_id, None)
            if binding and binding.session_id in self._by_session:
                if self._by_session[binding.session_id] == kv_id:
                    self._by_session.pop(binding.session_id, None)

    def to_handle(
        self,
        kv_id: str,
        *,
        provider: ProviderName = ProviderName.RAM,
        location: str = "",
        share_token: str = "",
    ) -> KVHandle:
        return KVHandle(
            kv_id=kv_id,
            provider=provider,
            location=location,
            share_token=share_token,
        )
