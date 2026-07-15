"""PolicyOptimizer port — produces immutable RuntimePolicy objects."""

from __future__ import annotations

from abc import ABC, abstractmethod

from neuroswarm_arm.evolution.interfaces.reflection import PolicyDelta
from neuroswarm_arm.evolution.models.experiment import CandidatePolicy
from neuroswarm_arm.evolution.models.policy import RuntimePolicy


class PolicyOptimizer(ABC):
    @abstractmethod
    def materialize(
        self,
        delta: PolicyDelta,
        *,
        parent: RuntimePolicy | None = None,
        version: str | None = None,
    ) -> CandidatePolicy:
        raise NotImplementedError

    def materialize_many(
        self,
        deltas: list[PolicyDelta],
        *,
        parent: RuntimePolicy | None = None,
    ) -> list[CandidatePolicy]:
        return [self.materialize(d, parent=parent) for d in deltas]
