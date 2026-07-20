"""RuntimeOptimizer — full AROP pipeline controller."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from neuroswarm_arm.evolution.bus.events import AROPEventType, EventBus
from neuroswarm_arm.evolution.config import AROPConfig
from neuroswarm_arm.evolution.deployment.engine import DeploymentEngine
from neuroswarm_arm.evolution.evolution.engine import LineageEvolutionEngine
from neuroswarm_arm.evolution.experiment.engine import ExperimentEngine
from neuroswarm_arm.evolution.interfaces.reflection import PolicyDelta, ReflectionStrategy
from neuroswarm_arm.evolution.knowledge.engine import KnowledgeEngine
from neuroswarm_arm.evolution.models.experiment import ExperimentStatus
from neuroswarm_arm.evolution.models.observation import Episode, Outcome, Reward, TimeWindow
from neuroswarm_arm.evolution.models.policy import RuntimePolicy
from neuroswarm_arm.evolution.observation.aggregator import MetricsAggregator
from neuroswarm_arm.evolution.optimization.engine import OptimizationEngine
from neuroswarm_arm.evolution.optimization.policy_registry import PolicyRegistry
from neuroswarm_arm.evolution.rl.experience_store import ExperienceStore, OfflineContextualBandit
from neuroswarm_arm.evolution.safety.engine import SafetyEngine
from neuroswarm_arm.evolution.validation.engine import ValidationEngine


@dataclass
class PipelineResult:
    status: str
    baseline_id: str | None = None
    candidate_id: str | None = None
    policy_id: str | None = None
    message: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


class RuntimeOptimizer:
    """
    Observe → Normalize → Store → Analyze → Reflect → Generate Candidates →
    Offline Eval → Shadow → Statistical Validation → Safety → Canary →
    Monitor → Rollback/Knowledge Update.
    """

    def __init__(
        self,
        config: AROPConfig,
        *,
        aggregator: MetricsAggregator,
        knowledge: KnowledgeEngine,
        reflection: ReflectionStrategy,
        optimization: OptimizationEngine,
        experiment: ExperimentEngine,
        validation: ValidationEngine,
        safety: SafetyEngine,
        deployment: DeploymentEngine,
        evolution: LineageEvolutionEngine,
        registry: PolicyRegistry,
        bus: EventBus | None = None,
        experience: ExperienceStore | None = None,
        bandit: OfflineContextualBandit | None = None,
    ) -> None:
        self.config = config
        self.aggregator = aggregator
        self.knowledge = knowledge
        self.reflection = reflection
        self.optimization = optimization
        self.experiment = experiment
        self.validation = validation
        self.safety = safety
        self.deployment = deployment
        self.evolution = evolution
        self.registry = registry
        self.bus = bus or EventBus()
        self.experience = experience or ExperienceStore()
        self.bandit = bandit or OfflineContextualBandit()
        self.enabled = config.enabled
        self._last_result: PipelineResult | None = None

    def ensure_baseline(self) -> RuntimePolicy:
        active = self.registry.active()
        if active:
            return active
        baseline = RuntimePolicy.create(
            policy_id=f"pol_baseline_{uuid.uuid4().hex[:8]}",
            version="v0",
            parameters={
                "accept_threshold": self.config.default_accept_threshold,
                "draft_len": self.config.default_draft_len,
                "escalate_threshold": self.config.default_escalate_threshold,
                "reasoning_cap": self.config.default_reasoning_cap,
                "router_top_k": self.config.default_router_top_k,
                "verify_batch": 1,
                "speculation_depth": 1,
            },
            target_layers=frozenset({"ascr", "rtg", "router"}),
            expected_reward=0.0,
            confidence=1.0,
            explanation="initial baseline",
        )
        self.registry.register(baseline)
        self.registry.set_active(baseline.id)
        self.knowledge.record_policy(baseline)
        self.evolution.record(baseline)
        return baseline

    def run_once(self) -> PipelineResult:
        if not self.enabled:
            return PipelineResult(status="disabled", message="AROP disabled")

        baseline = self.ensure_baseline()

        # 1–3 Observe → Normalize → Store
        observations = self.aggregator.collect(TimeWindow.last_seconds(300))
        self.knowledge.ingest(observations)
        self.bus.emit(AROPEventType.OBSERVATION_COLLECTED, n=len(observations))

        view = self.knowledge.view()
        self.bus.emit(AROPEventType.KNOWLEDGE_UPDATED, metrics=dict(view.aggregate_metrics))

        # Collect offline RL experience from aggregate
        state = {k: float(v) for k, v in view.aggregate_metrics.items()}
        if state:
            self.experience.add(
                state,
                dict(baseline.parameters),
                float(view.aggregate_metrics.get("reward_scalar", baseline.expected_reward)),
                state,
                policy_id=baseline.id,
            )

        # 4–6 Analyze → Reflect → Generate candidates
        recommendation = self.reflection.recommend(view)
        deltas: list[PolicyDelta] = list(recommendation.deltas)

        if self.config.bandit_enabled and len(self.experience.buffer) > 0:
            self.bandit.fit(self.experience.buffer.all())
            deltas.extend(self.bandit.propose(state or dict(baseline.parameters)))

        self.bus.emit(AROPEventType.POLICY_PROPOSED, n=len(deltas))
        if not deltas:
            result = PipelineResult(
                status="noop",
                baseline_id=baseline.id,
                message="no policy deltas proposed",
                metrics=dict(view.aggregate_metrics),
            )
            self._last_result = result
            return result

        candidates = self.optimization.materialize_many(deltas, parent=baseline)
        candidate = candidates[0]
        self.bus.emit(
            AROPEventType.POLICY_MATERIALIZED,
            policy_id=candidate.policy.id,
            candidate_id=candidate.candidate_id,
        )

        # 7 Offline evaluation
        offline = self.experiment.run_offline(candidate, baseline=baseline)
        self.bus.emit(AROPEventType.OFFLINE_EVAL_DONE, score=offline.offline_score)

        # 8 Shadow execution
        shadow_deploy = self.deployment.deploy_shadow(candidate)
        shadow = self.experiment.run_shadow(candidate, baseline=baseline)
        self.bus.emit(AROPEventType.SHADOW_DONE, score=shadow.shadow_score)

        # 9 Statistical validation
        validation = self.validation.validate(
            candidate, baseline=baseline, offline=offline, shadow=shadow
        )
        self.bus.emit(
            AROPEventType.VALIDATION_DONE,
            passed=validation.passed,
            p_value=validation.p_value,
        )

        # 10 Safety verification
        safety = self.safety.check(
            candidate,
            baseline=baseline,
            validation=validation,
            live_metrics=validation.metrics_candidate,
        )
        self.bus.emit(AROPEventType.SAFETY_DONE, passed=safety.passed)

        if not validation.passed or not safety.passed:
            self.knowledge.store.store_reflection(
                f"rejected:{candidate.policy.id}:{validation.message}:{safety.message}"
            )
            self.bus.emit(
                AROPEventType.PIPELINE_REJECTED,
                reason=validation.message if not validation.passed else safety.message,
            )
            result = PipelineResult(
                status="rejected",
                baseline_id=baseline.id,
                candidate_id=candidate.candidate_id,
                policy_id=candidate.policy.id,
                message=safety.message if not safety.passed else validation.message,
                metrics=dict(validation.metrics_candidate),
                details={
                    "validation": validation.message,
                    "safety": safety.message,
                    "shadow": shadow_deploy.message,
                },
            )
            self._last_result = result
            return result

        # 11 Canary deployment
        canary = self.deployment.deploy_canary(
            candidate, percent=self.config.canary_percent
        )
        canary_result = self.experiment.run_canary(
            candidate, baseline=baseline, percent=self.config.canary_percent
        )
        self.bus.emit(
            AROPEventType.CANARY_DEPLOYED,
            percent=self.config.canary_percent,
            policy_id=candidate.policy.id,
        )

        # 12 Continuous monitoring (single-shot MVP check)
        monitor_ok = canary_result.canary_score >= baseline.expected_reward - 1e-6
        if not monitor_ok:
            rb = self.deployment.rollback(to_policy=baseline)
            self.knowledge.store.store_reflection(
                f"rollback:{candidate.policy.id}:{rb.message}"
            )
            self.bus.emit(AROPEventType.ROLLED_BACK, policy_id=baseline.id)
            # Knowledge update
            ep = Episode(
                episode_id=f"ep_{uuid.uuid4().hex[:10]}",
                started_at=datetime.now(timezone.utc),
                ended_at=datetime.now(timezone.utc),
                policy_id=candidate.policy.id,
                policy_version=candidate.policy.version,
                observations=tuple(observations[-10:]),
                outcome=Outcome(
                    success=False,
                    reward=Reward.scalarize(
                        latency_ms=float(validation.metrics_candidate.get("latency_ms", 0)),
                        accept_rate=float(validation.metrics_candidate.get("accept_rate", 0)),
                    ),
                    notes="canary_regression",
                ),
            )
            self.knowledge.record_episode(ep)
            result = PipelineResult(
                status="rolled_back",
                baseline_id=baseline.id,
                candidate_id=candidate.candidate_id,
                policy_id=candidate.policy.id,
                message=rb.message,
                metrics=dict(canary_result.metrics),
            )
            self._last_result = result
            return result

        # Promote if configured; else leave canary running
        if self.config.auto_promote:
            promo = self.deployment.promote(candidate)
            self.bus.emit(AROPEventType.PROMOTED, policy_id=candidate.policy.id)
            promote_msg = promo.message
            status = ExperimentStatus.PROMOTED.value
        else:
            promote_msg = "canary active; auto_promote disabled"
            status = ExperimentStatus.CANARY.value

        # 13 Knowledge update + lineage
        updated = RuntimePolicy.create(
            policy_id=candidate.policy.id,
            version=candidate.policy.version,
            parameters=candidate.policy.parameters,
            target_layers=candidate.policy.target_layers,
            expected_reward=float(canary_result.canary_score),
            confidence=candidate.policy.confidence,
            constraints=candidate.policy.constraints,
            rollback_policy_id=baseline.id,
            parent_policy_id=baseline.id,
            explanation=candidate.policy.explanation,
        )
        # Keep same id registered; update expected reward via re-register not possible (frozen).
        # Record lineage on original candidate policy.
        path = self.knowledge.record_policy(candidate.policy)
        self.evolution.record(candidate.policy, okf_path=str(path) if path else None)
        self.knowledge.store.store_reflection(
            f"deployed:{candidate.policy.id}:{promote_msg}"
        )

        ep = Episode(
            episode_id=f"ep_{uuid.uuid4().hex[:10]}",
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            policy_id=candidate.policy.id,
            policy_version=candidate.policy.version,
            observations=tuple(observations[-10:]),
            outcome=Outcome(
                success=True,
                reward=Reward.scalarize(
                    latency_ms=float(validation.metrics_candidate.get("latency_ms", 0)),
                    accept_rate=float(validation.metrics_candidate.get("accept_rate", 0.7)),
                    quality=float(validation.metrics_candidate.get("quality", 1.0)),
                ),
                notes=status,
            ),
        )
        self.knowledge.record_episode(ep)
        self.experience.add(
            state or dict(baseline.parameters),
            dict(candidate.policy.parameters),
            float(canary_result.canary_score),
            state or dict(candidate.policy.parameters),
            policy_id=candidate.policy.id,
            done=True,
        )

        self.bus.emit(AROPEventType.PIPELINE_COMPLETE, status=status, policy_id=candidate.policy.id)
        result = PipelineResult(
            status=status,
            baseline_id=baseline.id,
            candidate_id=candidate.candidate_id,
            policy_id=candidate.policy.id,
            message=promote_msg,
            metrics=dict(canary_result.metrics),
            details={
                "canary": canary.message,
                "validation": validation.message,
                "safety": safety.message,
                "unused_updated_hash": updated.content_hash,
            },
        )
        self._last_result = result
        return result

    def run_forever(self) -> None:
        while self.enabled:
            self.run_once()
            time.sleep(max(1, self.config.interval_seconds))

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "registry": self.registry.status(),
            "last": None
            if self._last_result is None
            else {
                "status": self._last_result.status,
                "policy_id": self._last_result.policy_id,
                "message": self._last_result.message,
            },
            "experience_n": len(self.experience),
            "events": [
                {"type": e.type.value, "at": e.at.isoformat()} for e in self.bus.history(limit=10)
            ],
        }

    def health(self) -> dict[str, Any]:
        def _provider_healthy(provider: Any) -> bool:
            h = provider.health()
            if isinstance(h, dict):
                return bool(h.get("healthy", True))
            return bool(getattr(h, "healthy", True))

        return {
            "healthy": True,
            "plane": "arop",
            "providers": {
                p.name: {"healthy": _provider_healthy(p)} for p in self.aggregator.providers
            },
            "registry": self.registry.status(),
        }
