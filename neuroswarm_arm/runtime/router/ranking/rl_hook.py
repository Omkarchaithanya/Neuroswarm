"""Reinforcement learning extension hook for routing."""

from __future__ import annotations

from typing import Protocol

from ..models import RouteContext


class RLRoutingHook(Protocol):
    def adjust(
        self,
        tool_id: str,
        score: float,
        features: dict[str, float],
        context: RouteContext | None,
    ) -> float: ...

    def observe_reward(self, tool_id: str, reward: float, features: dict[str, float] | None = None) -> None: ...


class NoOpRLHook:
    def adjust(
        self,
        tool_id: str,
        score: float,
        features: dict[str, float],
        context: RouteContext | None,
    ) -> float:
        return score

    def observe_reward(self, tool_id: str, reward: float, features: dict[str, float] | None = None) -> None:
        return None


class BanditRLHook:
    """Epsilon-free soft bandit: boost historically rewarded tools."""

    def __init__(self) -> None:
        self._rewards: dict[str, float] = {}
        self._counts: dict[str, int] = {}

    def adjust(
        self,
        tool_id: str,
        score: float,
        features: dict[str, float],
        context: RouteContext | None,
    ) -> float:
        n = self._counts.get(tool_id, 0)
        if n <= 0:
            return score
        avg = self._rewards.get(tool_id, 0.0) / n
        return 0.85 * score + 0.15 * avg

    def observe_reward(self, tool_id: str, reward: float, features: dict[str, float] | None = None) -> None:
        self._rewards[tool_id] = self._rewards.get(tool_id, 0.0) + float(reward)
        self._counts[tool_id] = self._counts.get(tool_id, 0) + 1
