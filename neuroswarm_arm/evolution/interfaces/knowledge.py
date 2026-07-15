"""Knowledge store ports — Mem0 runtime memory + OKF engineering memory."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from neuroswarm_arm.evolution.models.observation import Episode, NormalizedObservation, Outcome
from neuroswarm_arm.evolution.models.policy import RuntimePolicy


@dataclass(frozen=True, slots=True)
class KnowledgeView:
    """Read model for reflection / optimization."""

    recent_observations: tuple[NormalizedObservation, ...] = ()
    recent_episodes: tuple[Episode, ...] = ()
    active_policy: RuntimePolicy | None = None
    aggregate_metrics: Mapping[str, float] = field(default_factory=dict)
    reflections: tuple[str, ...] = ()
    extras: Mapping[str, Any] = field(default_factory=dict)


class KnowledgeStore(ABC):
    @abstractmethod
    def store_observation(self, obs: NormalizedObservation) -> None:
        raise NotImplementedError

    @abstractmethod
    def store_episode(self, episode: Episode) -> None:
        raise NotImplementedError

    @abstractmethod
    def store_outcome(self, episode_id: str, outcome: Outcome) -> None:
        raise NotImplementedError

    @abstractmethod
    def store_policy(self, policy: RuntimePolicy) -> None:
        raise NotImplementedError

    @abstractmethod
    def store_reflection(self, text: str, *, metadata: Mapping[str, Any] | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def view(self, *, limit: int = 50) -> KnowledgeView:
        raise NotImplementedError

    def store_observations(self, observations: Sequence[NormalizedObservation]) -> None:
        for obs in observations:
            self.store_observation(obs)
