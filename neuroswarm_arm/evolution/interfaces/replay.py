"""Replay buffer / engine ports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from neuroswarm_arm.evolution.models.experience import Experience
from neuroswarm_arm.evolution.models.experiment import CandidatePolicy
from neuroswarm_arm.evolution.models.observation import Episode


class ReplayBuffer(ABC):
    @abstractmethod
    def add(self, experience: Experience) -> None:
        raise NotImplementedError

    @abstractmethod
    def sample(self, n: int) -> list[Experience]:
        raise NotImplementedError

    @abstractmethod
    def __len__(self) -> int:
        raise NotImplementedError

    def extend(self, experiences: Sequence[Experience]) -> None:
        for exp in experiences:
            self.add(exp)


class ReplayEngine(ABC):
    """Re-run recorded workloads under a candidate policy."""

    @abstractmethod
    def record_episode(self, episode: Episode) -> None:
        raise NotImplementedError

    @abstractmethod
    def replay(
        self,
        candidate: CandidatePolicy,
        *,
        max_episodes: int = 50,
    ) -> dict[str, float]:
        """Return aggregate metrics from replaying under candidate parameters."""
        raise NotImplementedError
