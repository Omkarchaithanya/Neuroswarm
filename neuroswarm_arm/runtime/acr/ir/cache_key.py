"""ContextCacheKey — version-aware cache identity."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass(slots=True)
class ContextCacheKey:
    tier: str  # hot | warm | assembly | compression | memory | knowledge | planning | prompt | numa | shared
    request_fingerprint: str
    plan_hash: str = ""
    version_hash: str = ""
    owner: str = ""
    agent_role: str = ""
    extra: dict = field(default_factory=dict)

    def digest(self) -> str:
        raw = "|".join(
            [
                self.tier,
                self.request_fingerprint,
                self.plan_hash,
                self.version_hash,
                self.owner,
                self.agent_role,
                str(sorted(self.extra.items())),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
