"""Composition tests."""

from __future__ import annotations

import pytest

from neuroswarm_arm.runtime.swarm.sub_swarms import (
    CircularCompositionError,
    SwarmComposer,
    SwarmProfile,
    ResourceProfile,
)


def test_clone(sample_template):
    composer = SwarmComposer()
    cloned = composer.clone(sample_template, new_id="x.clone", new_name="x_clone")
    assert cloned.id == "x.clone"
    assert sample_template.id in cloned.metadata.provenance


def test_extend(sample_template):
    composer = SwarmComposer()
    extended = composer.extend(
        sample_template,
        extra_agents=["nexus.agents.coding_agent"],
        extra_tools=["nexus.tools.github"],
        tags=["extended"],
    )
    assert "nexus.agents.coding_agent" in extended.required_agents
    assert "nexus.tools.github" in extended.required_tools
    assert "extended" in extended.tags
    assert sample_template.id in extended.metadata.composition_of


def test_override(sample_template):
    composer = SwarmComposer()
    overridden = composer.override(sample_template, priority=99, new_name="over")
    assert overridden.priority == 99
    assert overridden.name == "over"


def test_merge(sample_template):
    composer = SwarmComposer()
    other = sample_template.clone(new_id="nexus.swarms.other", new_name="other").evolve(
        required_agents=["nexus.agents.memory_agent"],
        estimated_cost=0.05,
    )
    merged = composer.merge(sample_template, other, new_id="nexus.swarms.merged")
    assert merged.id == "nexus.swarms.merged"
    assert "nexus.agents.memory_agent" in merged.required_agents
    assert merged.estimated_cost == 0.05


def test_parameterize(sample_template):
    composer = SwarmComposer()
    param = composer.parameterize(
        sample_template,
        {"priority": 88, "repo": "nexus"},
    )
    assert param.priority == 88
    assert param.metadata.extra["parameters"]["repo"] == "nexus"


def test_to_executable(sample_template):
    desc = SwarmComposer().to_executable(
        sample_template, parameters={"request": "hello"}
    )
    assert desc.template_id == sample_template.id
    assert desc.agents == sample_template.required_agents
    assert desc.task_graph.graph_id == sample_template.task_graph_reference.graph_id


def test_circular_merge_same_id(sample_template):
    composer = SwarmComposer()
    with pytest.raises(CircularCompositionError):
        composer.merge(sample_template, sample_template)


def test_profile_merge(sample_template):
    other = SwarmProfile(resource=ResourceProfile(memory_bytes=999, cpu_cores=9.0))
    merged = sample_template.profile.merge(other)
    assert merged.resource.memory_bytes == 999
