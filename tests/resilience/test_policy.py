"""Policy evaluation tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.resilience import PolicyEngine, ResiliencePolicy, default_policy

from .conftest import make_plan, make_policy, make_signals


def test_default_policy_chain():
    policy = default_policy()
    engine = PolicyEngine([policy])
    chain = engine.chain_for(policy, "Qwen3-8B")
    assert chain[0] == "Qwen3-3B"
    assert "TinyLlama" in chain


def test_match_preferred_model():
    engine = PolicyEngine([default_policy()])
    matched = engine.match(make_plan(model="Qwen3-8B"), make_signals())
    assert matched is not None
    assert matched.policy_id == "default"


def test_higher_priority_wins():
    low = make_policy(policy_id="low", priority=1.0)
    high = make_policy(policy_id="high", priority=10.0, name="high")
    engine = PolicyEngine([low, high])
    matched = engine.match(make_plan(), make_signals())
    assert matched is not None
    assert matched.policy_id == "high"


def test_register_replaces_same_id():
    engine = PolicyEngine()
    engine.register(ResiliencePolicy(policy_id="p1", preferred_models=["A"], priority=1))
    engine.register(ResiliencePolicy(policy_id="p1", preferred_models=["B"], priority=2))
    assert len(engine.policies) == 1
    assert engine.get("p1").preferred_models == ["B"]
