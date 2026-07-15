"""Offline RL experience store + contextual bandit."""

from __future__ import annotations

import math
import threading
import uuid
from collections import defaultdict
from typing import Any, Mapping

from neuroswarm_arm.evolution.interfaces.reflection import PolicyDelta
from neuroswarm_arm.evolution.models.experience import Experience
from neuroswarm_arm.evolution.optimization.knobs import layers_for_parameters
from neuroswarm_arm.evolution.replay.buffer import InMemoryReplayBuffer


class ExperienceStore:
    def __init__(self, buffer: InMemoryReplayBuffer | None = None) -> None:
        self.buffer = buffer or InMemoryReplayBuffer()

    def add(
        self,
        state: Mapping[str, float],
        action: Mapping[str, Any],
        reward: float,
        next_state: Mapping[str, float],
        *,
        policy_id: str | None = None,
        done: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> Experience:
        exp = Experience(
            experience_id=f"xp_{uuid.uuid4().hex[:10]}",
            state=dict(state),
            action=dict(action),
            reward=float(reward),
            next_state=dict(next_state),
            policy_id=policy_id,
            done=done,
            metadata=dict(metadata or {}),
        )
        self.buffer.add(exp)
        return exp

    def __len__(self) -> int:
        return len(self.buffer)


class OfflineContextualBandit:
    """Mean-reward UCB bandit over discrete action arms (offline fit → propose)."""

    def __init__(self, *, alpha: float = 0.5) -> None:
        self.alpha = alpha
        self._lock = threading.RLock()
        self._counts: dict[str, int] = defaultdict(int)
        self._values: dict[str, float] = defaultdict(float)
        self._actions: dict[str, dict[str, Any]] = {}

    def _arm_key(self, action: Mapping[str, Any]) -> str:
        return str(sorted((k, action[k]) for k in sorted(action.keys())))

    def update(self, action: Mapping[str, Any], reward: float) -> None:
        key = self._arm_key(action)
        with self._lock:
            self._actions[key] = dict(action)
            n = self._counts[key]
            value = self._values[key]
            self._counts[key] = n + 1
            self._values[key] = value + (reward - value) / (n + 1)

    def fit(self, experiences: list[Experience]) -> None:
        for exp in experiences:
            self.update(exp.action, exp.reward)

    def propose(self, state: Mapping[str, float], *, n: int = 1) -> list[PolicyDelta]:
        with self._lock:
            if not self._values:
                return [self._cold_start(state)]

            total = sum(self._counts.values()) or 1

            def ucb(k: str) -> float:
                return self._values[k] + self.alpha * math.sqrt(
                    math.log(total + 1) / max(self._counts[k], 1)
                )

            ranked = sorted(self._values.keys(), key=ucb, reverse=True)
            out: list[PolicyDelta] = []
            for key in ranked[: max(1, n)]:
                action = self._actions.get(key, {"draft_len": 8})
                out.append(
                    PolicyDelta(
                        parameters=action,
                        target_layers=layers_for_parameters(action),
                        rationale=f"bandit_ucb:{key[:48]}",
                        expected_reward=float(self._values[key]),
                        confidence=min(0.85, 0.3 + 0.05 * self._counts[key]),
                        source="bandit",
                    )
                )
            return out

    def _cold_start(self, state: Mapping[str, float]) -> PolicyDelta:
        accept = float(state.get("accept_rate", state.get("ascr_accept_rate", 0.7)))
        latency = float(state.get("latency_ms", state.get("ascr_latency_ms", 1000)))
        if accept < 0.6:
            params: dict[str, Any] = {
                "accept_threshold": min(0.95, accept + 0.05),
                "draft_len": 6,
            }
        elif latency > 2500:
            params = {"draft_len": 4, "reasoning_cap": 256}
        else:
            params = {"draft_len": 10}
        return PolicyDelta(
            parameters=params,
            target_layers=layers_for_parameters(params),
            rationale="bandit_cold_start",
            expected_reward=0.05,
            confidence=0.4,
            source="bandit",
        )


class OfflineRLTrainer:
    """Stub interface for future CQL/IQL — currently delegates to bandit."""

    def __init__(self, bandit: OfflineContextualBandit | None = None) -> None:
        self.bandit = bandit or OfflineContextualBandit()

    def train(self, experiences: list[Experience]) -> OfflineContextualBandit:
        self.bandit.fit(experiences)
        return self.bandit

    def propose(self, state: Mapping[str, float]) -> list[PolicyDelta]:
        return self.bandit.propose(state)
