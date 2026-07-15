"""Replay buffer + engine for offline regression under candidate policies."""

from __future__ import annotations

import random
import threading
from collections import deque
from typing import Deque

from neuroswarm_arm.evolution.interfaces.replay import ReplayBuffer, ReplayEngine
from neuroswarm_arm.evolution.models.experience import Experience
from neuroswarm_arm.evolution.models.experiment import CandidatePolicy
from neuroswarm_arm.evolution.models.observation import Episode
from neuroswarm_arm.evolution.models.policy import RuntimePolicy


class InMemoryReplayBuffer(ReplayBuffer):
    def __init__(self, capacity: int = 10_000) -> None:
        self._buf: Deque[Experience] = deque(maxlen=capacity)
        self._lock = threading.RLock()

    def add(self, experience: Experience) -> None:
        with self._lock:
            self._buf.append(experience)

    def sample(self, n: int) -> list[Experience]:
        with self._lock:
            if not self._buf:
                return []
            k = min(n, len(self._buf))
            return random.sample(list(self._buf), k)

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)

    def all(self) -> list[Experience]:
        with self._lock:
            return list(self._buf)


class EpisodeReplayEngine(ReplayEngine):
    """Heuristic replay: score candidate params against recorded episode metrics."""

    def __init__(self, *, max_store: int = 500) -> None:
        self._episodes: Deque[Episode] = deque(maxlen=max_store)
        self._lock = threading.RLock()

    def record_episode(self, episode: Episode) -> None:
        with self._lock:
            self._episodes.append(episode)

    def replay(
        self,
        candidate: CandidatePolicy,
        *,
        max_episodes: int = 50,
    ) -> dict[str, float]:
        with self._lock:
            eps = list(self._episodes)[-max_episodes:]
        if not eps:
            # Synthetic baseline when no history yet
            return self._score_synthetic(candidate.policy)

        scores: list[float] = []
        latencies: list[float] = []
        accepts: list[float] = []
        for ep in eps:
            base = 0.0
            if ep.outcome is not None:
                base = ep.outcome.reward.scalar
                latencies.append(ep.outcome.reward.latency_ms)
                accepts.append(ep.outcome.reward.accept_rate)
            # Penalize aggressive draft when historical accept was low
            draft = float(candidate.policy.parameters.get("draft_len", 8))
            accept_thr = float(candidate.policy.parameters.get("accept_threshold", 0.7))
            hist_accept = accepts[-1] if accepts else 0.7
            adj = base
            if draft > 16 and hist_accept < 0.6:
                adj -= 0.1
            if accept_thr > 0.9 and hist_accept > 0.8:
                adj += 0.02
            scores.append(adj)

        return {
            "replay_n": float(len(eps)),
            "reward_scalar": sum(scores) / max(len(scores), 1),
            "latency_ms": sum(latencies) / max(len(latencies), 1) if latencies else 0.0,
            "accept_rate": sum(accepts) / max(len(accepts), 1) if accepts else 0.7,
        }

    def _score_synthetic(self, policy: RuntimePolicy) -> dict[str, float]:
        draft = float(policy.parameters.get("draft_len", 8))
        accept = float(policy.parameters.get("accept_threshold", 0.7))
        reasoning = float(policy.parameters.get("reasoning_cap", 512))
        # Prefer moderate draft, mid accept, bounded reasoning
        score = 0.5
        score += 0.1 if 4 <= draft <= 16 else -0.05
        score += 0.1 if 0.55 <= accept <= 0.85 else -0.05
        score += 0.05 if reasoning <= 1024 else -0.05
        return {
            "replay_n": 0.0,
            "reward_scalar": score,
            "latency_ms": 1000.0 + draft * 20,
            "accept_rate": accept,
        }
