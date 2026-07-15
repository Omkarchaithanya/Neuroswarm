"""Experiment engine — offline / shadow / canary orchestration."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from neuroswarm_arm.evolution.interfaces.experiment import ExperimentRunner
from neuroswarm_arm.evolution.interfaces.replay import ReplayEngine
from neuroswarm_arm.evolution.models.experiment import (
    CandidatePolicy,
    ExperimentResult,
    ExperimentStatus,
)
from neuroswarm_arm.evolution.models.policy import RuntimePolicy


class ExperimentEngine(ExperimentRunner):
    def __init__(self, replay: ReplayEngine, *, canary_percent: float = 10.0) -> None:
        self.replay = replay
        self.canary_percent = canary_percent

    def run_offline(
        self,
        candidate: CandidatePolicy,
        *,
        baseline: RuntimePolicy | None = None,
    ) -> ExperimentResult:
        metrics = self.replay.replay(candidate, max_episodes=50)
        baseline_score = baseline.expected_reward if baseline else 0.0
        score = float(metrics.get("reward_scalar", 0.0))
        return ExperimentResult(
            experiment_id=f"exp_{uuid.uuid4().hex[:10]}",
            candidate=candidate,
            baseline_policy_id=baseline.id if baseline else None,
            status=ExperimentStatus.OFFLINE_EVAL,
            offline_score=score,
            metrics={**metrics, "baseline_reward": baseline_score},
            message=f"offline reward={score:.4f}",
            finished_at=datetime.now(timezone.utc),
        )

    def run_shadow(
        self,
        candidate: CandidatePolicy,
        *,
        baseline: RuntimePolicy | None = None,
    ) -> ExperimentResult:
        # Shadow = dry replay with candidate; compare to baseline expected
        metrics = self.replay.replay(candidate, max_episodes=30)
        score = float(metrics.get("reward_scalar", 0.0))
        base = baseline.expected_reward if baseline else 0.0
        return ExperimentResult(
            experiment_id=f"exp_{uuid.uuid4().hex[:10]}",
            candidate=candidate,
            baseline_policy_id=baseline.id if baseline else None,
            status=ExperimentStatus.SHADOW,
            shadow_score=score,
            offline_score=score,
            metrics={**metrics, "shadow_delta": score - base},
            message=f"shadow reward={score:.4f} delta={score - base:.4f}",
            finished_at=datetime.now(timezone.utc),
        )

    def run_canary(
        self,
        candidate: CandidatePolicy,
        *,
        baseline: RuntimePolicy | None = None,
        percent: float = 10.0,
    ) -> ExperimentResult:
        metrics = self.replay.replay(candidate, max_episodes=20)
        score = float(metrics.get("reward_scalar", 0.0))
        return ExperimentResult(
            experiment_id=f"exp_{uuid.uuid4().hex[:10]}",
            candidate=candidate,
            baseline_policy_id=baseline.id if baseline else None,
            status=ExperimentStatus.CANARY,
            canary_score=score,
            metrics={**metrics, "canary_percent": float(percent)},
            message=f"canary {percent}% reward={score:.4f}",
            finished_at=datetime.now(timezone.utc),
        )
