"""Health scoring for registered agents."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ._utils import clamp, utc_now


class HealthRecord(BaseModel):
    """Mutable health snapshot attached to an agent."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    score: float = 1.0
    availability: float = 1.0
    failure_count: int = 0
    success_count: int = 0
    success_rate: float = 1.0
    average_latency_ms: float = 0.0
    average_cost_usd: float = 0.0
    last_execution: datetime | None = None
    last_heartbeat: datetime | None = None
    consecutive_failures: int = 0
    status_message: str = "ok"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("score", "availability", "success_rate")
    @classmethod
    def _unit(cls, v: float) -> float:
        return clamp(float(v), 0.0, 1.0)

    @field_validator("failure_count", "success_count", "consecutive_failures")
    @classmethod
    def _non_neg(cls, v: int) -> int:
        if v < 0:
            raise ValueError("must be >= 0")
        return v

    @property
    def is_healthy(self) -> bool:
        return self.score >= 0.5 and self.availability >= 0.5

    def band(self) -> str:
        if self.score >= 0.8:
            return "healthy"
        if self.score >= 0.5:
            return "degraded"
        return "unhealthy"

    def record_success(self, *, latency_ms: float = 0.0, cost_usd: float = 0.0) -> HealthRecord:
        sc = self.success_count + 1
        total = sc + self.failure_count
        avg_lat = _ema(self.average_latency_ms, latency_ms, sc)
        avg_cost = _ema(self.average_cost_usd, cost_usd, sc)
        rate = sc / total if total else 1.0
        score = clamp(0.5 * rate + 0.5 * self.availability, 0.0, 1.0)
        return self.model_copy(
            update={
                "success_count": sc,
                "success_rate": rate,
                "average_latency_ms": avg_lat,
                "average_cost_usd": avg_cost,
                "last_execution": utc_now(),
                "consecutive_failures": 0,
                "score": score,
                "status_message": "ok",
            }
        )

    def record_failure(self, *, message: str = "failure") -> HealthRecord:
        fc = self.failure_count + 1
        total = self.success_count + fc
        rate = self.success_count / total if total else 0.0
        consec = self.consecutive_failures + 1
        avail = clamp(self.availability * 0.95, 0.0, 1.0)
        score = clamp(0.5 * rate + 0.5 * avail, 0.0, 1.0)
        return self.model_copy(
            update={
                "failure_count": fc,
                "success_rate": rate,
                "consecutive_failures": consec,
                "availability": avail,
                "score": score,
                "last_execution": utc_now(),
                "status_message": message,
            }
        )

    def touch_heartbeat(self) -> HealthRecord:
        return self.model_copy(
            update={
                "last_heartbeat": utc_now(),
                "availability": clamp(min(1.0, self.availability + 0.05), 0.0, 1.0),
                "score": clamp(
                    0.5 * self.success_rate
                    + 0.5 * clamp(min(1.0, self.availability + 0.05), 0.0, 1.0),
                    0.0,
                    1.0,
                ),
            }
        )


def _ema(prev: float, sample: float, n: int, alpha: float | None = None) -> float:
    if n <= 1:
        return sample
    a = alpha if alpha is not None else 2.0 / (n + 1)
    return (1.0 - a) * prev + a * sample
