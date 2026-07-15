"""Safety gate port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Mapping

from neuroswarm_arm.evolution.interfaces.validation import ValidationReport
from neuroswarm_arm.evolution.models.experiment import CandidatePolicy
from neuroswarm_arm.evolution.models.policy import RuntimePolicy


@dataclass(frozen=True, slots=True)
class SafetyReport:
    passed: bool
    violations: tuple[str, ...] = ()
    checks: Mapping[str, bool] = field(default_factory=dict)
    message: str = ""


class SafetyGate(ABC):
    @abstractmethod
    def check(
        self,
        candidate: CandidatePolicy,
        *,
        baseline: RuntimePolicy | None,
        validation: ValidationReport | None = None,
        live_metrics: Mapping[str, float] | None = None,
    ) -> SafetyReport:
        raise NotImplementedError
