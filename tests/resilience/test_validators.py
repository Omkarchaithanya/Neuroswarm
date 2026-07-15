"""Validator tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.resilience import (
    AlternativeExecutionPlan,
    ModelProfile,
    ResiliencePolicy,
    ResilienceValidator,
    ValidationError,
)

from .conftest import make_plan


def test_invalid_profile():
    v = ResilienceValidator()
    with pytest.raises(ValidationError):
        v.validate_profile(
            ModelProfile(model_id="", quantizations=["Q4_K_M"], supported_backends=["llama_cpp"])
        )


def test_invalid_policy():
    v = ResilienceValidator()
    with pytest.raises(ValidationError):
        v.validate_policy(ResiliencePolicy(policy_id="", min_health_score=0.5))


def test_invalid_snapshot():
    v = ResilienceValidator()
    with pytest.raises(ValidationError):
        v.validate_snapshot(make_plan(model=""))


def test_valid_alternative():
    v = ResilienceValidator()
    v.validate_alternative(
        AlternativeExecutionPlan(plan_id="p1", model="Gemma", backend="llama_cpp")
    )
