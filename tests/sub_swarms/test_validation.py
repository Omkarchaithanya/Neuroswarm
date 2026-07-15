"""Validation tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.sub_swarms import (
    SwarmBuilder,
    SwarmValidator,
    ValidationError,
)


def test_validate_ok(sample_template):
    report = SwarmValidator().validate(sample_template)
    assert report.ok
    assert not report.errors


def test_missing_task_graph():
    tpl = (
        SwarmBuilder()
        .template(id="nexus.swarms.bad_graph", name="bad_graph")
        .agents("nexus.agents.planning_agent")
        .build()
    )
    report = SwarmValidator().validate(tpl)
    assert not report.ok
    assert any(i.code == "missing_task_graph" for i in report.errors)


def test_missing_agents():
    tpl = (
        SwarmBuilder()
        .template(id="nexus.swarms.bad_agents", name="bad_agents")
        .task_graph(graph_id="g", snapshot={"nodes": {}})
        .build()
    )
    report = SwarmValidator().validate(tpl)
    assert not report.ok
    assert any(i.code == "missing_agents" for i in report.errors)


def test_unknown_agent_ids(sample_template):
    report = SwarmValidator().validate(
        sample_template,
        known_agent_ids=["nexus.agents.other"],
    )
    assert not report.ok
    assert any(i.code == "unknown_agent" for i in report.errors)


def test_strict_raises():
    tpl = (
        SwarmBuilder()
        .template(id="nexus.swarms.strict", name="strict")
        .agents("a")
        .build()
    )
    with pytest.raises(ValidationError):
        SwarmValidator().validate(tpl, strict=True)


def test_circular_composition_flag(sample_template):
    bad = sample_template.evolve(
        metadata=sample_template.metadata.model_copy(
            update={"composition_of": [sample_template.id]}
        )
    )
    report = SwarmValidator().validate(bad)
    assert any(i.code == "circular_composition" for i in report.errors)
