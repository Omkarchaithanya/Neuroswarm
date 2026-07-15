"""Experiment / candidate policy models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from .policy import RuntimePolicy


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExperimentStatus(str, Enum):
    PENDING = "pending"
    OFFLINE_EVAL = "offline_eval"
    SHADOW = "shadow"
    STAT_VALIDATION = "stat_validation"
    SAFETY = "safety"
    CANARY = "canary"
    MONITORING = "monitoring"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CandidatePolicy:
    candidate_id: str
    policy: RuntimePolicy
    source: str  # rule|gepa|bandit|hybrid|human
    created_at: datetime = field(default_factory=_utcnow)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    experiment_id: str
    candidate: CandidatePolicy
    baseline_policy_id: str | None
    status: ExperimentStatus
    offline_score: float = 0.0
    shadow_score: float = 0.0
    canary_score: float = 0.0
    p_value: float | None = None
    safety_passed: bool = False
    metrics: Mapping[str, float] = field(default_factory=dict)
    message: str = ""
    finished_at: datetime | None = None
