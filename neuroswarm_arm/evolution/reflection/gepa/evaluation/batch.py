"""
GEPA evaluation batch types.

Maps to official: ``gepa.core.adapter.EvaluationBatch``
(https://github.com/gepa-ai/gepa/blob/main/src/gepa/core/adapter.py)

ArmCascade/AROP: evaluation results feed Pareto acceptance and ASI construction;
never mutates hardware or ASCR thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

Trajectory = TypeVar("Trajectory")
RolloutOutput = TypeVar("RolloutOutput")


@dataclass
class EvaluationBatch(Generic[Trajectory, RolloutOutput]):
    """Result of evaluating a text candidate on a data batch.

    Official contract: scores higher-is-better; trajectories opaque to the
    engine and consumed by ``make_reflective_dataset``.
    """

    outputs: list[RolloutOutput]
    scores: list[float]
    trajectories: list[Trajectory] | None = None
    objective_scores: list[dict[str, float]] | None = None
    num_metric_calls: int | None = None

    def sum_scores(self) -> float:
        return float(sum(self.scores)) if self.scores else 0.0

    def mean_score(self) -> float:
        return self.sum_scores() / max(len(self.scores), 1)
