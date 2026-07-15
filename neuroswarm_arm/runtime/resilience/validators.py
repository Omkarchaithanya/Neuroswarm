"""Structural validators for profiles, policies, and plans."""

from __future__ import annotations

from .exceptions import ValidationError
from .execution import AlternativeExecutionPlan, ExecutionSnapshot
from .models import ModelProfile
from .policy import ResiliencePolicy


class ResilienceValidator:
    """Validate RMRE domain objects before engine use / serialization."""

    def validate_profile(self, profile: ModelProfile) -> None:
        if not profile.model_id.strip():
            raise ValidationError("model_id required", field="model_id")
        if profile.context_length <= 0:
            raise ValidationError("context_length must be > 0", field="context_length")
        if profile.parameter_count < 0:
            raise ValidationError("parameter_count must be >= 0", field="parameter_count")
        if not profile.quantizations:
            raise ValidationError("quantizations required", field="quantizations")
        if not profile.supported_backends:
            raise ValidationError(
                "supported_backends required", field="supported_backends"
            )
        if profile.estimated_latency < 0:
            raise ValidationError("estimated_latency must be >= 0", field="estimated_latency")
        if profile.estimated_cost < 0:
            raise ValidationError("estimated_cost must be >= 0", field="estimated_cost")
        if profile.estimated_memory < 0:
            raise ValidationError("estimated_memory must be >= 0", field="estimated_memory")

    def validate_policy(self, policy: ResiliencePolicy) -> None:
        if not policy.policy_id.strip():
            raise ValidationError("policy_id required", field="policy_id")
        if policy.failure_threshold < 0:
            raise ValidationError(
                "failure_threshold must be >= 0", field="failure_threshold"
            )
        if not (0.0 <= policy.min_health_score <= 1.0):
            raise ValidationError(
                "min_health_score must be in [0,1]", field="min_health_score"
            )
        if policy.max_latency_ms <= 0:
            raise ValidationError("max_latency_ms must be > 0", field="max_latency_ms")
        for model_id, chain in policy.fallback_chains.items():
            if not model_id:
                raise ValidationError("empty fallback chain key", field="fallback_chains")
            if any(not c for c in chain):
                raise ValidationError(
                    f"empty entry in chain for {model_id}", field="fallback_chains"
                )

    def validate_snapshot(self, plan: ExecutionSnapshot) -> None:
        if not plan.model.strip():
            raise ValidationError("model required", field="model")
        if not plan.backend.strip():
            raise ValidationError("backend required", field="backend")
        if plan.context_length <= 0:
            raise ValidationError("context_length must be > 0", field="context_length")
        if plan.thread_count <= 0:
            raise ValidationError("thread_count must be > 0", field="thread_count")

    def validate_alternative(self, alt: AlternativeExecutionPlan) -> None:
        if not alt.plan_id.strip():
            raise ValidationError("plan_id required", field="plan_id")
        if not alt.model.strip():
            raise ValidationError("model required", field="model")
        if not alt.backend.strip():
            raise ValidationError("backend required", field="backend")
