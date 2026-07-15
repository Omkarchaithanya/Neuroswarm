"""Sharing engine — multi-reader, single-owner handles."""

from __future__ import annotations

from threading import RLock

from .exceptions import KVPermissionError
from .models import SharePermission
from .utils import new_token


class SharingEngine:
    def __init__(self) -> None:
        self._perms: dict[str, SharePermission] = {}  # token -> perm
        self._by_kv: dict[str, set[str]] = {}  # kv_id -> tokens
        self._lock = RLock()

    def grant(
        self,
        kv_id: str,
        owner: str,
        consumer: str,
        *,
        can_read: bool = True,
        can_write: bool = False,
    ) -> SharePermission:
        token = new_token()
        perm = SharePermission(
            kv_id=kv_id,
            owner=owner,
            consumer=consumer,
            can_read=can_read,
            can_write=can_write,
            token=token,
        )
        with self._lock:
            self._perms[token] = perm
            self._by_kv.setdefault(kv_id, set()).add(token)
        return perm

    def revoke(self, token: str) -> None:
        with self._lock:
            perm = self._perms.pop(token, None)
            if perm is None:
                return
            tokens = self._by_kv.get(perm.kv_id)
            if tokens is not None:
                tokens.discard(token)
                if not tokens:
                    self._by_kv.pop(perm.kv_id, None)

    def revoke_all(self, kv_id: str) -> None:
        with self._lock:
            tokens = self._by_kv.pop(kv_id, set())
            for t in tokens:
                self._perms.pop(t, None)

    def check_read(self, kv_id: str, agent_id: str, token: str = "") -> bool:
        with self._lock:
            if token:
                perm = self._perms.get(token)
                if perm is None or perm.kv_id != kv_id:
                    return False
                return perm.can_read and (perm.consumer == agent_id or perm.owner == agent_id)
            # Owner always reads; any granted consumer
            for t in self._by_kv.get(kv_id, set()):
                perm = self._perms[t]
                if perm.owner == agent_id:
                    return True
                if perm.consumer == agent_id and perm.can_read:
                    return True
            return False

    def require_read(self, kv_id: str, agent_id: str, token: str = "") -> None:
        if not self.check_read(kv_id, agent_id, token):
            # Allow empty agent (system) for internal ops
            if agent_id:
                raise KVPermissionError(f"read denied kv={kv_id} agent={agent_id}")

    def consumers(self, kv_id: str) -> list[str]:
        with self._lock:
            out: list[str] = []
            for t in self._by_kv.get(kv_id, set()):
                out.append(self._perms[t].consumer)
            return out
