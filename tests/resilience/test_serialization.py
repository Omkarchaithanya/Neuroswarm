"""Serialization tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.resilience import (
    ModelProfile,
    ResilienceSerializer,
    default_policy,
)

from .conftest import make_catalog, make_plan


def test_profile_roundtrip_json():
    ser = ResilienceSerializer()
    profile = make_catalog()["Qwen3-8B"]
    raw = ser.dumps_profile(profile)
    loaded = ser.loads_profile(raw)
    assert loaded.model_id == profile.model_id
    assert loaded.parameter_count == profile.parameter_count


def test_policy_roundtrip_json():
    ser = ResilienceSerializer()
    policy = default_policy()
    raw = ser.dumps_policy(policy)
    loaded = ser.loads_policy(raw)
    assert loaded.policy_id == policy.policy_id
    assert loaded.fallback_chains["Qwen3-8B"][0] == "Qwen3-3B"


def test_snapshot_roundtrip():
    ser = ResilienceSerializer()
    snap = make_plan()
    raw = ser.dumps_snapshot(snap)
    loaded = ser.loads_snapshot(raw)
    assert loaded.model == snap.model
    assert loaded.backend == snap.backend


def test_yaml_roundtrip():
    import pytest

    pytest.importorskip("yaml")
    ser = ResilienceSerializer()
    profile = make_catalog()["Gemma"]
    raw = ser.dumps_profile(profile, fmt="yaml")
    loaded = ser.loads_profile(raw, fmt="yaml")
    assert loaded.model_id == "Gemma"


def test_dict_roundtrip():
    ser = ResilienceSerializer()
    profile = make_catalog()["TinyLlama"]
    payload = ser.dumps_dict(profile, kind="ModelProfile")
    loaded = ser.loads_dict(payload, ModelProfile)
    assert loaded.family == "llama"
