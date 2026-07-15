"""Session ACL / capability tokens (no MTE)."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from threading import RLock


@dataclass
class Capability:
    token: str
    session_id: str
    agent_id: str
    can_read: bool = True
    can_write: bool = False
    can_share: bool = False
    expires_at: float = 0.0


@dataclass
class AccessPolicy:
    """Capability-token based access control for shared KV blocks."""

    ttl_s: float = 3600.0
    _caps: dict[str, Capability] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def issue(
        self,
        session_id: str,
        agent_id: str,
        *,
        can_write: bool = False,
        can_share: bool = False,
    ) -> Capability:
        token = secrets.token_urlsafe(24)
        cap = Capability(
            token=token,
            session_id=session_id,
            agent_id=agent_id,
            can_read=True,
            can_write=can_write,
            can_share=can_share,
            expires_at=time.time() + self.ttl_s,
        )
        with self._lock:
            self._caps[token] = cap
        return cap

    def revoke(self, token: str) -> None:
        with self._lock:
            self._caps.pop(token, None)

    def authorize(
        self,
        token: str,
        session_id: str,
        *,
        write: bool = False,
        share: bool = False,
    ) -> bool:
        with self._lock:
            cap = self._caps.get(token)
            if cap is None:
                return False
            if cap.expires_at and time.time() > cap.expires_at:
                self._caps.pop(token, None)
                return False
            if cap.session_id != session_id:
                return False
            if write and not cap.can_write:
                return False
            if share and not cap.can_share:
                return False
            return True
