"""Offline RL experience tuples."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class Experience:
    """(state, action, reward, next_state) for offline RL / bandits."""

    experience_id: str
    state: Mapping[str, float]
    action: Mapping[str, Any]
    reward: float
    next_state: Mapping[str, float]
    policy_id: str | None = None
    done: bool = False
    collected_at: datetime = field(default_factory=_utcnow)
    metadata: Mapping[str, Any] = field(default_factory=dict)
