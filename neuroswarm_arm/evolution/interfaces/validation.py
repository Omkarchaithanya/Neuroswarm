"""Validation port — TTFT/TPS/quality/ARM PMU scorecard."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Mapping

from neuroswarm_arm.evolution.models.experiment import CandidatePolicy, ExperimentResult
from neuroswarm_arm.evolution.models.policy import RuntimePolicy


@dataclass(frozen=True, slots=True)
class ValidationReport:
    passed: bool
    p_value: float | None
    effect_size: float
    metrics_baseline: Mapping[str, float] = field(default_factory=dict)
    metrics_candidate: Mapping[str, float] = field(default_factory=dict)
    message: str = ""


class Validator(ABC):
    @abstractmethod
    def validate(
        self,
        candidate: CandidatePolicy,
        *,
        baseline: RuntimePolicy | None,
        offline: ExperimentResult | None = None,
        shadow: ExperimentResult | None = None,
    ) -> ValidationReport:
        raise NotImplementedError
