"""Execution quality scores — deterministic / manual / automatic, no LLM eval."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from .models import _Frozen
from ._utils import clamp


class QualityScore(_Frozen):
    """Multi-dimension quality for a completed execution.

    No LLM-as-judge fields. Automatic scores come from runtime heuristics
    (latency/budget objectives, tool success rates, workflow completion).
    """

    execution: float = 0.0
    tool_correctness: float = 0.0
    workflow_completion: float = 0.0
    latency_objective: float = 0.0
    budget_objective: float = 0.0
    manual: float | None = None
    automatic: float | None = None
    overall: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "execution",
        "tool_correctness",
        "workflow_completion",
        "latency_objective",
        "budget_objective",
    )
    @classmethod
    def _unit_interval(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("quality dimension must be in [0, 1]")
        return v

    @field_validator("manual", "automatic", "overall")
    @classmethod
    def _opt_unit(cls, v: float | None) -> float | None:
        if v is None:
            return v
        if v < 0.0 or v > 1.0:
            raise ValueError("quality score must be in [0, 1]")
        return v

    @model_validator(mode="after")
    def _derive_overall(self) -> QualityScore:
        if self.overall is not None:
            return self
        dims = [
            self.execution,
            self.tool_correctness,
            self.workflow_completion,
            self.latency_objective,
            self.budget_objective,
        ]
        if self.manual is not None:
            dims.append(self.manual)
        if self.automatic is not None:
            dims.append(self.automatic)
        computed = sum(dims) / len(dims) if dims else 0.0
        object.__setattr__(self, "overall", clamp(computed, 0.0, 1.0))
        return self

    @property
    def score(self) -> float:
        """Primary scalar used by indexes / analytics."""
        return float(self.overall if self.overall is not None else 0.0)
