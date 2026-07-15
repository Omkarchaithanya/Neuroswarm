"""Experiment runner port."""

from __future__ import annotations

from abc import ABC, abstractmethod

from neuroswarm_arm.evolution.models.experiment import CandidatePolicy, ExperimentResult
from neuroswarm_arm.evolution.models.policy import RuntimePolicy


class ExperimentRunner(ABC):
    @abstractmethod
    def run_offline(
        self,
        candidate: CandidatePolicy,
        *,
        baseline: RuntimePolicy | None = None,
    ) -> ExperimentResult:
        raise NotImplementedError

    @abstractmethod
    def run_shadow(
        self,
        candidate: CandidatePolicy,
        *,
        baseline: RuntimePolicy | None = None,
    ) -> ExperimentResult:
        raise NotImplementedError

    @abstractmethod
    def run_canary(
        self,
        candidate: CandidatePolicy,
        *,
        baseline: RuntimePolicy | None = None,
        percent: float = 10.0,
    ) -> ExperimentResult:
        raise NotImplementedError
