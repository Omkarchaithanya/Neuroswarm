"""Constraint tests."""

from __future__ import annotations

from neuroswarm_arm.runtime.swarm.sub_swarms import (
    SwarmConstraints,
    SwarmValidator,
)


def test_agent_count_ok():
    c = SwarmConstraints(min_agents=2, max_agents=4)
    assert c.agent_count_ok(2)
    assert c.agent_count_ok(4)
    assert not c.agent_count_ok(1)
    assert not c.agent_count_ok(5)


def test_within_budget():
    c = SwarmConstraints(max_cost_usd=0.01, max_latency_ms=5000.0)
    assert c.within_budget(cost=0.005, latency_ms=1000.0)
    assert not c.within_budget(cost=0.02, latency_ms=1000.0)
    assert not c.within_budget(cost=0.005, latency_ms=9000.0)


def test_validator_budget_limits(sample_template):
    tight = sample_template.evolve(
        constraints=SwarmConstraints(
            min_agents=1,
            max_cost_usd=0.0001,
        ),
        estimated_cost=0.01,
    )
    report = SwarmValidator().validate(tight)
    assert any(i.code == "budget_limits" for i in report.errors)
